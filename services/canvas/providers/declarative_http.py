"""Restricted JSON/multipart adapter for vetted third-party image APIs.

The stored document is deliberately *data*, not a general templating language:
only exact ``{{variable}}`` leaves from a small allowlist are substituted.  The
adapter never accepts an absolute endpoint, callback URL, executable expression
or caller-selected header/query key.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
import secrets
from dataclasses import dataclass
from typing import Any, Literal, Mapping
from urllib.parse import quote, urlsplit

from config import CANVAS_REMOTE_IMAGE_MAX_BYTES
from services.canvas.provider_network import ProviderNetworkError, validate_relative_endpoint
from services.canvas.provider_schemas import (
    ControlledImageBytes,
    ControlledRemoteImage,
    ModelCapabilities,
    ProviderCancelResult,
    ProviderError,
    ProviderGenerationRequest,
    ProviderPollResult,
    ProviderRecoveryResult,
    ProviderRecoveryUnsupported,
    ProviderRequestValidationError,
    ProviderRuntime,
    ProviderSubmission,
)


_VARIABLES = frozenset({
    "model_id", "prompt", "negative_prompt", "quantity", "ratio", "width", "height",
    "reference_image_bytes", "reference_image_base64", "mask_bytes", "seed",
})
_TEMPLATE = re.compile(r"^\{\{([a-z_]+)\}\}$")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_HEADER = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
_PATH_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
_FORBIDDEN_KEYS = frozenset({"__proto__", "prototype", "constructor"})
_FIXED_HEADERS = frozenset({"accept", "content-type", "user-agent"})
_FORBIDDEN_HEADERS = frozenset({
    "authorization", "host", "cookie", "connection", "content-length",
    "transfer-encoding", "proxy-authorization", "x-forwarded-host",
})
_METHODS = frozenset({"POST", "PUT", "GET", "DELETE"})


class DeclarativeConfigurationError(ValueError):
    """The administrator-supplied adapter document is outside the safe DSL."""


@dataclass(frozen=True)
class _Auth:
    kind: Literal["none", "bearer", "api_key_header", "api_key_query"]
    name: str | None = None


@dataclass(frozen=True)
class _Operation:
    method: str
    endpoint: str


@dataclass(frozen=True)
class _ImageResult:
    image_type: Literal["base64", "url", "binary"]
    image_path: tuple[str | int, ...] | None


@dataclass(frozen=True)
class _AsyncResult:
    task_id_path: tuple[str | int, ...]
    poll: _Operation
    status_path: tuple[str | int, ...]
    pending_values: frozenset[str]
    completed_values: frozenset[str]
    image: _ImageResult
    cancel: _Operation | None


@dataclass(frozen=True)
class _Configuration:
    auth: _Auth
    fixed_headers: Mapping[str, str]
    submit: _Operation
    submit_format: Literal["json", "multipart"]
    submit_json: Mapping[str, object] | None
    multipart_fields: Mapping[str, object] | None
    multipart_files: Mapping[str, str] | None
    sync_image: _ImageResult | None
    asynchronous: _AsyncResult | None


def _mapping(value: object, label: str, *, max_items: int = 64) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > max_items:
        raise DeclarativeConfigurationError(f"{label} must be a bounded object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _KEY.fullmatch(key) or key.lower() in _FORBIDDEN_KEYS:
            raise DeclarativeConfigurationError(f"{label} has an invalid key")
        result[key] = item
    return result


def _string(value: object, label: str, *, limit: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or "\r" in value or "\n" in value:
        raise DeclarativeConfigurationError(f"{label} is invalid")
    return value


def _ensure_plain_value(value: object, label: str, *, depth: int = 0) -> None:
    if depth > 12:
        raise DeclarativeConfigurationError(f"{label} is too deeply nested")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        template = _TEMPLATE.fullmatch(value)
        if "{{" in value or "}}" in value:
            if template is None or template.group(1) not in _VARIABLES:
                raise DeclarativeConfigurationError(f"{label} contains an unsupported template")
        if "://" in value:
            raise DeclarativeConfigurationError(f"{label} must not contain an external URL")
        return
    if isinstance(value, list):
        if len(value) > 100:
            raise DeclarativeConfigurationError(f"{label} is too large")
        for child in value:
            _ensure_plain_value(child, label, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, child in _mapping(value, label).items():
            _ensure_plain_value(child, label, depth=depth + 1)
        return
    raise DeclarativeConfigurationError(f"{label} contains an unsupported value")


def _compile_path(value: object, label: str) -> tuple[str | int, ...]:
    raw = _string(value, label, limit=1024)
    tokens: list[str | int] = []
    cursor = 0
    expect_key = True
    while cursor < len(raw):
        if expect_key:
            match = _PATH_KEY.match(raw, cursor)
            if match is None:
                raise DeclarativeConfigurationError(f"{label} is invalid")
            key = match.group(0)
            if key.lower() in _FORBIDDEN_KEYS:
                raise DeclarativeConfigurationError(f"{label} is invalid")
            tokens.append(key)
            cursor = match.end()
            expect_key = False
        elif raw.startswith(".", cursor):
            cursor += 1
            expect_key = True
        elif raw.startswith("[", cursor):
            end = raw.find("]", cursor + 1)
            if end < 0 or not raw[cursor + 1:end].isdigit():
                raise DeclarativeConfigurationError(f"{label} is invalid")
            index = int(raw[cursor + 1:end])
            if index > 99:
                raise DeclarativeConfigurationError(f"{label} is invalid")
            tokens.append(index)
            cursor = end + 1
        else:
            raise DeclarativeConfigurationError(f"{label} is invalid")
        if len(tokens) > 12:
            raise DeclarativeConfigurationError(f"{label} is too deep")
    if expect_key:
        raise DeclarativeConfigurationError(f"{label} is invalid")
    return tuple(tokens)


def _compile_operation(value: object, label: str, *, task_endpoint: bool = False) -> _Operation:
    document = _mapping(value, label, max_items=8)
    method = _string(document.get("method"), f"{label}.method", limit=8).upper()
    if method not in _METHODS:
        raise DeclarativeConfigurationError(f"{label}.method is not allowed")
    endpoint = _string(document.get("endpoint"), f"{label}.endpoint")
    if task_endpoint:
        if endpoint.count("{external_task_id}") != 1:
            raise DeclarativeConfigurationError(f"{label}.endpoint must contain one task identifier")
        trial = endpoint.replace("{external_task_id}", "task-id")
    else:
        if "{" in endpoint or "}" in endpoint:
            raise DeclarativeConfigurationError(f"{label}.endpoint cannot be templated")
        trial = endpoint
    try:
        validate_relative_endpoint(trial)
    except ProviderNetworkError as exc:
        raise DeclarativeConfigurationError(f"{label}.endpoint is invalid") from exc
    return _Operation(method=method, endpoint=endpoint)


def _compile_image_result(value: object, label: str, *, max_items: int = 4) -> _ImageResult:
    document = _mapping(value, label, max_items=max_items)
    image_type = _string(document.get("imageType"), f"{label}.imageType", limit=16).lower()
    if image_type not in {"base64", "url", "binary"}:
        raise DeclarativeConfigurationError(f"{label}.imageType is invalid")
    path = document.get("imagePath")
    if image_type == "binary":
        if path is not None:
            raise DeclarativeConfigurationError(f"{label}.imagePath is not used for binary results")
        return _ImageResult(image_type="binary", image_path=None)
    return _ImageResult(
        image_type=image_type,  # type: ignore[arg-type]
        image_path=_compile_path(path, f"{label}.imagePath"),
    )


def compile_declarative_configuration(value: object) -> _Configuration:
    document = _mapping(value, "model configuration", max_items=8)
    auth_doc = _mapping(document.get("auth", {}), "auth", max_items=2)
    auth_type = _string(auth_doc.get("type", "none"), "auth.type", limit=32).lower()
    if auth_type not in {"none", "bearer", "api_key_header", "api_key_query"}:
        raise DeclarativeConfigurationError("auth.type is invalid")
    auth_name = auth_doc.get("name")
    if auth_type in {"api_key_header", "api_key_query"}:
        auth_name = _string(auth_name, "auth.name", limit=64)
        if not _HEADER.fullmatch(auth_name) or auth_name.lower() in _FORBIDDEN_HEADERS:
            raise DeclarativeConfigurationError("auth.name is invalid")
    elif auth_name is not None:
        raise DeclarativeConfigurationError("auth.name is only valid for API-key authentication")
    headers_doc = _mapping(document.get("headers", {}), "headers", max_items=8)
    headers: dict[str, str] = {}
    for name, raw_value in headers_doc.items():
        if not _HEADER.fullmatch(name) or name.lower() not in _FIXED_HEADERS:
            raise DeclarativeConfigurationError("headers contain a disallowed name")
        fixed = _string(raw_value, f"headers.{name}", limit=512)
        if "{{" in fixed or "}}" in fixed or "://" in fixed:
            raise DeclarativeConfigurationError("headers must be fixed non-secret values")
        headers[name] = fixed
    if any(name.lower() == str(auth_name).lower() for name in headers) if auth_name else False:
        raise DeclarativeConfigurationError("headers must not override API-key authentication")
    submit_doc = _mapping(document.get("submit"), "submit", max_items=8)
    submit = _compile_operation(submit_doc, "submit")
    submit_format = _string(submit_doc.get("format"), "submit.format", limit=16).lower()
    if submit_format not in {"json", "multipart"}:
        raise DeclarativeConfigurationError("submit.format is invalid")
    submit_json = submit_doc.get("json")
    multipart_fields = submit_doc.get("fields")
    multipart_files = submit_doc.get("files")
    if submit_format == "json":
        if "json" not in submit_doc or multipart_fields is not None or multipart_files is not None:
            raise DeclarativeConfigurationError("JSON submit configuration is invalid")
        submit_json = _mapping(submit_json, "submit.json")
        _ensure_plain_value(submit_json, "submit.json")
        if _contains_variable(submit_json, {"reference_image_bytes", "mask_bytes"}):
            raise DeclarativeConfigurationError("binary image variables require multipart")
        multipart_fields = None
        multipart_files = None
    else:
        if "fields" not in submit_doc or "json" in submit_doc:
            raise DeclarativeConfigurationError("multipart submit configuration is invalid")
        multipart_fields = _mapping(multipart_fields, "submit.fields")
        _ensure_plain_value(multipart_fields, "submit.fields")
        files_doc = _mapping(multipart_files or {}, "submit.files")
        multipart_files = {}
        for field_name, variable in files_doc.items():
            if variable not in {"reference_image_bytes", "mask_bytes"}:
                raise DeclarativeConfigurationError("multipart file fields are invalid")
            multipart_files[field_name] = str(variable)
        submit_json = None
    result_doc = _mapping(document.get("result"), "result", max_items=8)
    mode = _string(result_doc.get("mode"), "result.mode", limit=16).lower()
    if mode == "sync":
        if any(key in result_doc for key in ("taskIdPath", "poll", "cancel")):
            raise DeclarativeConfigurationError("sync result configuration is invalid")
        return _Configuration(
            auth=_Auth(kind=auth_type, name=auth_name),  # type: ignore[arg-type]
            fixed_headers=headers, submit=submit, submit_format=submit_format, submit_json=submit_json,
            multipart_fields=multipart_fields, multipart_files=multipart_files,
            sync_image=_compile_image_result(result_doc, "result"), asynchronous=None,
        )
    if mode != "async":
        raise DeclarativeConfigurationError("result.mode is invalid")
    poll_doc = _mapping(result_doc.get("poll"), "result.poll", max_items=12)
    poll = _compile_operation(poll_doc, "result.poll", task_endpoint=True)
    pending = _enum_values(poll_doc.get("pendingValues"), "result.poll.pendingValues")
    completed = _enum_values(poll_doc.get("completedValues"), "result.poll.completedValues")
    if pending & completed:
        raise DeclarativeConfigurationError("poll status values overlap")
    cancel = None
    if "cancel" in result_doc:
        cancel = _compile_operation(result_doc["cancel"], "result.cancel", task_endpoint=True)
        if cancel.method not in {"POST", "DELETE"}:
            raise DeclarativeConfigurationError("result.cancel.method is invalid")
    return _Configuration(
        auth=_Auth(kind=auth_type, name=auth_name),  # type: ignore[arg-type]
        fixed_headers=headers, submit=submit, submit_format=submit_format, submit_json=submit_json,
        multipart_fields=multipart_fields, multipart_files=multipart_files, sync_image=None,
        asynchronous=_AsyncResult(
            task_id_path=_compile_path(result_doc.get("taskIdPath"), "result.taskIdPath"), poll=poll,
            status_path=_compile_path(poll_doc.get("statusPath"), "result.poll.statusPath"),
            pending_values=pending, completed_values=completed,
            image=_compile_image_result(poll_doc, "result.poll", max_items=12), cancel=cancel,
        ),
    )


def _contains_variable(value: object, names: set[str]) -> bool:
    if isinstance(value, str):
        match = _TEMPLATE.fullmatch(value)
        return match is not None and match.group(1) in names
    if isinstance(value, list):
        return any(_contains_variable(item, names) for item in value)
    if isinstance(value, dict):
        return any(_contains_variable(item, names) for item in value.values())
    return False


def _enum_values(value: object, label: str) -> frozenset[str]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise DeclarativeConfigurationError(f"{label} is invalid")
    results = frozenset(_string(item, label, limit=100) for item in value)
    if len(results) != len(value):
        raise DeclarativeConfigurationError(f"{label} is invalid")
    return results


def _lookup(document: object, path: tuple[str | int, ...]) -> object:
    current = document
    for token in path:
        if isinstance(token, str):
            if not isinstance(current, dict) or token not in current:
                raise ValueError
            current = current[token]
        else:
            if not isinstance(current, list) or token >= len(current):
                raise ValueError
            current = current[token]
    return current


def _json_document(response: object) -> object:
    content_type = getattr(response, "header")("content-type") or ""
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise ValueError
    return json.loads(getattr(response, "body").decode("utf-8"))


def _image_from_response(response: object, image: _ImageResult) -> ControlledImageBytes | ControlledRemoteImage:
    if image.image_type == "binary":
        content_type = (getattr(response, "header")("content-type") or "").split(";", 1)[0].lower()
        data = getattr(response, "body")
        if not content_type.startswith("image/") or not isinstance(data, bytes) or not data or len(data) > CANVAS_REMOTE_IMAGE_MAX_BYTES:
            raise ValueError
        return ControlledImageBytes(data=data)
    document = _json_document(response)
    raw_value = _lookup(document, image.image_path or ())
    if not isinstance(raw_value, str) or not raw_value:
        raise ValueError
    if image.image_type == "base64":
        payload = raw_value.split(",", 1)[1] if raw_value.startswith("data:") and "," in raw_value else raw_value
        decoded = base64.b64decode(payload, validate=True)
        if not decoded or len(decoded) > CANVAS_REMOTE_IMAGE_MAX_BYTES:
            raise ValueError
        return ControlledImageBytes(data=decoded)
    parsed = urlsplit(raw_value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError
    return ControlledRemoteImage(remote_url=raw_value)


class DeclarativeHttpAdapter:
    adapter_type = "declarative_http"

    def __init__(self, *, model_id: str, capabilities: ModelCapabilities, configuration: object) -> None:
        if not isinstance(model_id, str) or not model_id or len(model_id) > 200:
            raise DeclarativeConfigurationError("model ID is invalid")
        self.model_id = model_id
        self.capabilities = capabilities
        self._configuration = compile_declarative_configuration(configuration)

    def validate_request(self, request: ProviderGenerationRequest, capabilities: ModelCapabilities) -> None:
        if not isinstance(request.prompt, str) or not request.prompt.strip() or len(request.prompt) > 8_000:
            raise ProviderRequestValidationError("provider_prompt_invalid", "A valid background prompt is required")
        width, height = _dimensions(request.size)
        if width <= 0 or height <= 0:
            raise ProviderRequestValidationError("provider_size_invalid", "A supported image size is required")
        if request.quantity < 1 or request.quantity > capabilities.max_quantity:
            raise ProviderRequestValidationError("provider_quantity_unsupported", "The selected quantity is not supported")
        if len(request.reference_images) > capabilities.max_reference_images:
            raise ProviderRequestValidationError("provider_reference_unsupported", "This model cannot accept that many product references")
        if request.reference_images:
            if not capabilities.image_to_image or capabilities.reference_transfer not in {"bytes", "base64"}:
                raise ProviderRequestValidationError("provider_reference_unsupported", "This model cannot accept protected product references")
            if not all(isinstance(item, bytes) and item for item in request.reference_images):
                raise ProviderRequestValidationError("provider_reference_invalid", "Product references must be validated image bytes")
        if request.upstream_idempotency_key is not None and not capabilities.supports_idempotency:
            raise ProviderRequestValidationError("provider_idempotency_unsupported", "This model does not support upstream idempotency")

    async def submit(self, request: ProviderGenerationRequest, runtime: ProviderRuntime) -> ProviderSubmission:
        self.validate_request(request, self.capabilities)
        response = await self._send_submit(request, runtime)
        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(response.status_code)
        try:
            if self._configuration.asynchronous is not None:
                document = _json_document(response)
                task_id = _lookup(document, self._configuration.asynchronous.task_id_path)
                if not isinstance(task_id, str) or not _safe_task_id(task_id):
                    raise ValueError
                return ProviderSubmission(status="pending", external_task_id=task_id)
            return ProviderSubmission(status="completed", image=_image_from_response(response, self._configuration.sync_image))  # type: ignore[arg-type]
        except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, binascii.Error):
            raise ProviderError("provider_response_invalid", "Image Provider returned an invalid response") from None

    async def poll(self, submission: ProviderSubmission, runtime: ProviderRuntime) -> ProviderPollResult:
        config = self._configuration.asynchronous
        if config is None:
            return ProviderPollResult(kind="unsupported")
        endpoint = self._task_endpoint(config.poll, submission.external_task_id)
        response = await self._send(config.poll.method, endpoint, runtime)
        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(response.status_code)
        try:
            document = _json_document(response)
            status = _lookup(document, config.status_path)
            if not isinstance(status, str):
                raise ValueError
            if status in config.pending_values:
                return ProviderPollResult(kind="pending")
            if status not in config.completed_values:
                return ProviderPollResult(kind="failed")
            return ProviderPollResult(kind="completed", image=_image_from_response(response, config.image))
        except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, binascii.Error):
            raise ProviderError("provider_response_invalid", "Image Provider returned an invalid response") from None

    async def cancel(self, submission: ProviderSubmission, runtime: ProviderRuntime) -> ProviderCancelResult:
        config = self._configuration.asynchronous
        if config is None or config.cancel is None or not self.capabilities.supports_cancel:
            return ProviderCancelResult(kind="unsupported")
        endpoint = self._task_endpoint(config.cancel, submission.external_task_id)
        response = await self._send(config.cancel.method, endpoint, runtime)
        if 200 <= response.status_code < 300:
            return ProviderCancelResult(kind="cancelled")
        if response.status_code in {404, 409, 410}:
            return ProviderCancelResult(kind="already_terminal")
        self._raise_http_error(response.status_code)
        raise AssertionError("unreachable")

    async def recover_by_idempotency_key(self, upstream_key: str, runtime: ProviderRuntime) -> ProviderRecoveryResult:
        return ProviderRecoveryUnsupported()

    async def _send_submit(self, request: ProviderGenerationRequest, runtime: ProviderRuntime):
        variables = self._variables(request)
        config = self._configuration
        headers, query = self._authentication(runtime)
        if request.upstream_idempotency_key is not None:
            headers["Idempotency-Key"] = request.upstream_idempotency_key
        if config.submit_format == "json":
            payload = _render(config.submit_json, variables)
            if not isinstance(payload, dict):
                raise ProviderError("provider_configuration_invalid", "Image Provider configuration is invalid")
            return await self._send(config.submit.method, config.submit.endpoint, runtime, headers=headers, query=query, json_body=payload)
        body, content_type = _multipart(config.multipart_fields or {}, config.multipart_files or {}, variables)
        headers["Content-Type"] = content_type
        return await self._send(config.submit.method, config.submit.endpoint, runtime, headers=headers, query=query, body=body)

    async def _send(self, method: str, endpoint: str, runtime: ProviderRuntime, *, headers: dict[str, str] | None = None, query: dict[str, str] | None = None, json_body: dict[str, object] | None = None, body: bytes | None = None):
        if not isinstance(runtime.api_key, str) or (self._configuration.auth.kind != "none" and not runtime.api_key):
            raise ProviderError("provider_missing_credential", "Image Provider credential is not configured")
        if headers is None:
            headers, default_query = self._authentication(runtime)
            if query is None:
                query = default_query
        kwargs: dict[str, object] = {"method": method, "endpoint": endpoint, "headers": headers, "max_bytes": CANVAS_REMOTE_IMAGE_MAX_BYTES}
        if query:
            kwargs["query"] = query
        if json_body is not None:
            kwargs["json_body"] = json_body
        if body is not None:
            kwargs["body"] = body
        try:
            return await runtime.transport.request(**kwargs)
        except ProviderNetworkError:
            raise ProviderError("provider_network_failed", "Image Provider request could not be completed", retryable=True) from None
        except Exception:
            raise ProviderError("provider_network_failed", "Image Provider request could not be completed", retryable=True) from None

    def _authentication(self, runtime: ProviderRuntime) -> tuple[dict[str, str], dict[str, str]]:
        headers = dict(self._configuration.fixed_headers)
        query: dict[str, str] = {}
        auth = self._configuration.auth
        if auth.kind == "bearer":
            headers["Authorization"] = f"Bearer {runtime.api_key}"
        elif auth.kind == "api_key_header":
            headers[auth.name or ""] = runtime.api_key
        elif auth.kind == "api_key_query":
            query[auth.name or ""] = runtime.api_key
        return headers, query

    def _variables(self, request: ProviderGenerationRequest) -> dict[str, object]:
        width, height = _dimensions(request.size)
        divisor = math.gcd(width, height)
        reference = request.reference_images[0] if request.reference_images else None
        return {
            "model_id": self.model_id, "prompt": request.prompt.strip(), "negative_prompt": "", "quantity": request.quantity,
            "ratio": f"{width // divisor}:{height // divisor}", "width": width, "height": height,
            "reference_image_bytes": reference, "reference_image_base64": base64.b64encode(reference).decode("ascii") if reference else None,
            "mask_bytes": None, "seed": None,
        }

    @staticmethod
    def _task_endpoint(operation: _Operation, task_id: str | None) -> str:
        if not isinstance(task_id, str) or not _safe_task_id(task_id):
            raise ProviderError("provider_task_invalid", "The saved Provider task identifier is invalid")
        return operation.endpoint.replace("{external_task_id}", quote(task_id, safe=""))

    @staticmethod
    def _raise_http_error(status_code: int) -> None:
        if status_code in {401, 403}:
            raise ProviderError("provider_authentication_failed", "Image Provider authentication failed", status_code=status_code)
        if status_code == 429:
            raise ProviderError("provider_rate_limited", "Image Provider is temporarily rate limited", retryable=True, status_code=status_code)
        raise ProviderError("provider_upstream_failed", "Image Provider returned an unsuccessful response", retryable=status_code >= 500, status_code=status_code)


def _dimensions(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]{1,4})x([1-9][0-9]{1,4})", value.strip() if isinstance(value, str) else "")
    if match is None:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _render(value: object, variables: Mapping[str, object]) -> object:
    if isinstance(value, str):
        match = _TEMPLATE.fullmatch(value)
        return variables[match.group(1)] if match is not None else value
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, variables) for key, item in value.items()}
    return value


def _multipart(fields: Mapping[str, object], files: Mapping[str, str], variables: Mapping[str, object]) -> tuple[bytes, str]:
    boundary = f"canvas-{secrets.token_hex(16)}"
    pieces: list[bytes] = []
    for name, value in _render(dict(fields), variables).items():
        if value is None or isinstance(value, (dict, list, bytes)):
            raise ProviderError("provider_configuration_invalid", "Image Provider configuration is invalid")
        pieces.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"])
    for field_name, variable in files.items():
        data = variables.get(variable)
        if data is None:
            continue
        if not isinstance(data, bytes) or not data or len(data) > CANVAS_REMOTE_IMAGE_MAX_BYTES:
            raise ProviderError("provider_reference_invalid", "Product references must be validated image bytes")
        pieces.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{field_name}"; filename="reference.png"\r\n'.encode(), b"Content-Type: image/png\r\n\r\n", data, b"\r\n"])
    pieces.append(f"--{boundary}--\r\n".encode())
    return b"".join(pieces), f"multipart/form-data; boundary={boundary}"


def _safe_task_id(value: str) -> bool:
    return bool(
        value and len(value) <= 200 and not any(part in value.lower() for part in ("..", "/", "?", "#", "%2f", "%25"))
        and "\r" not in value and "\n" not in value
    )


__all__ = ["DeclarativeConfigurationError", "DeclarativeHttpAdapter", "compile_declarative_configuration"]
