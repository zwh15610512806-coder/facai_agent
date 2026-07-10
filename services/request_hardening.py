"""HTTP 请求体上限及无 Content-Length 场景的流式计数。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse


JSON_BODY_LIMIT = 2 * 1024 * 1024
FORM_UPLOAD_LIMIT = 12 * 1024 * 1024
INSPIRATION_ATTACHMENT_LIMIT = 13 * 1024 * 1024
WORKBOOK_UPLOAD_LIMIT = 100 * 1024 * 1024


def request_body_limit_for(path: str, content_type: str) -> int:
    """按路由和媒体类型返回请求体上限（含 multipart 包装开销）。"""

    normalized_path = path.rstrip("/") or "/"
    media_type = (content_type or "").partition(";")[0].strip().lower()
    if normalized_path in {
        "/api/templates/viral/import-workbook",
        "/api/templates/import-workbook",
        "/api/templates/import-excel",
    }:
        return WORKBOOK_UPLOAD_LIMIT
    if normalized_path.startswith("/api/inspiration") and media_type == "multipart/form-data":
        return INSPIRATION_ATTACHMENT_LIMIT
    if media_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
        return FORM_UPLOAD_LIMIT
    return JSON_BODY_LIMIT


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """在 ASGI receive 层计数，避免分块请求绕过上限。"""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        limit = request_body_limit_for(scope.get("path", "/"), headers.get("content-type", ""))
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    await self._reject(scope, receive, send, limit)
                    return
            except ValueError:
                await JSONResponse(
                    {"detail": "Invalid Content-Length header"}, status_code=400
                )(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._reject(scope, receive, send, limit)

    @staticmethod
    async def _reject(scope, receive, send, limit: int) -> None:
        await JSONResponse(
            {"detail": "Request body too large", "max_bytes": limit},
            status_code=413,
        )(scope, receive, send)
