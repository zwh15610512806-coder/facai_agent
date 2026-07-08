"""Agentic RAG orchestration for AI-work product-context chats."""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


logger = logging.getLogger(__name__)
MAX_AGENT_TOOL_CALLS = 4
MAX_AGENT_SELF_CHECKS = 1


@dataclass
class InspirationAgentResult:
    product_context: dict[str, Any] = field(default_factory=lambda: {"used": False, "context": "", "products": []})
    sources: list[dict[str, Any]] = field(default_factory=list)
    agent_trace: list[dict[str, str]] = field(default_factory=list)


def _empty_product_context() -> dict[str, Any]:
    return {"used": False, "context": "", "products": []}


def _trace(tool: str, label: str, status: str, summary: str) -> dict[str, str]:
    return {
        "tool": str(tool or "")[:40],
        "label": str(label or "")[:40],
        "status": str(status or "success")[:20],
        "summary": str(summary or "")[:240],
    }


def _short_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:120]


def _product_count(product_context: dict[str, Any]) -> int:
    products = product_context.get("products") if isinstance(product_context, dict) else []
    return len(products) if isinstance(products, list) else 0


def _normalize_product_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _empty_product_context()
    products = value.get("products")
    if not isinstance(products, list):
        products = []
    context = str(value.get("context") or "")
    return {
        "used": bool(value.get("used") or context or products),
        "context": context,
        "products": products,
    }


def _normalize_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if url:
            sources.append({"title": title or "外网资料", "url": url, "snippet": snippet})
    return sources


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _call_product_context(
    product_context_func: Callable[..., Any] | None,
    message: str,
    db: Any,
    *,
    limit: int,
) -> dict[str, Any]:
    if product_context_func is None:
        return _empty_product_context()
    result = product_context_func(message, db, limit=limit, force=True)
    return _normalize_product_context(await _maybe_await(result))


async def _call_web_search(
    web_search_func: Callable[..., Any] | None,
    query: str,
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    if web_search_func is None or not query.strip():
        return []
    result = web_search_func(query.strip(), max_results=max_results)
    return _normalize_sources(await _maybe_await(result))


def _attachment_trace(attachments: Sequence[Any]) -> dict[str, str] | None:
    count = len([item for item in attachments if str(getattr(item, "text", "") or "").strip()])
    if not count:
        return None
    return _trace("attachment", "附件", "success", f"读取 {count} 个附件")


async def run_inspiration_agent(
    *,
    message: str,
    db: Any,
    product_context_enabled: bool,
    web_search_enabled: bool,
    attachments: Sequence[Any] | None = None,
    tool_mode: str = "chat",
    product_context_func: Callable[..., Any] | None = None,
    web_search_func: Callable[..., Any] | None = None,
    product_limit: int = 6,
    web_query: str | None = None,
    web_max_results: int = 5,
) -> InspirationAgentResult:
    """Collect grounded evidence for AI-work answers without exposing internal reasoning."""
    del tool_mode
    trace: list[dict[str, str]] = []
    product_context = _empty_product_context()
    sources: list[dict[str, Any]] = []
    tool_calls = 0

    if product_context_enabled and tool_calls < MAX_AGENT_TOOL_CALLS:
        tool_calls += 1
        try:
            product_context = await _call_product_context(
                product_context_func,
                message,
                db,
                limit=product_limit,
            )
            count = _product_count(product_context)
            if count:
                trace.append(_trace("product_rag", "产品资料", "success", f"命中 {count} 个产品"))
            else:
                trace.append(_trace("product_rag", "产品资料", "warning", "没有命中直接产品资料"))
        except Exception as exc:
            logger.warning("AI-work product RAG tool failed: %s", exc)
            trace.append(_trace("product_rag", "产品资料", "error", f"产品资料检索失败：{_short_error(exc)}"))

    if (
        product_context_enabled
        and not _product_count(product_context)
        and tool_calls < MAX_AGENT_TOOL_CALLS
        and product_context_func is not None
        and not any(step["status"] == "error" and step["tool"] == "product_rag" for step in trace)
    ):
        try:
            tool_calls += 1
            checked_context = await _call_product_context(
                product_context_func,
                f"{message} 产品资料",
                db,
                limit=product_limit,
            )
            if _product_count(checked_context):
                product_context = checked_context
                trace.append(_trace("product_rag", "产品补查", "success", f"补查命中 {_product_count(product_context)} 个产品"))
        except Exception as exc:
            logger.warning("AI-work product RAG self-check failed: %s", exc)
            trace.append(_trace("product_rag", "产品补查", "error", f"补查失败：{_short_error(exc)}"))

    if web_search_enabled and tool_calls < MAX_AGENT_TOOL_CALLS:
        tool_calls += 1
        query = (web_query or message or "").strip()
        try:
            sources = await _call_web_search(web_search_func, query, max_results=web_max_results)
            if sources:
                trace.append(_trace("web_search", "联网搜索", "success", f"找到 {len(sources)} 条外网资料"))
            else:
                trace.append(_trace("web_search", "联网搜索", "warning", "没有获取到可用外网资料"))
        except Exception as exc:
            logger.warning("AI-work web search tool failed: %s", exc)
            trace.append(_trace("web_search", "联网搜索", "error", f"联网搜索失败：{_short_error(exc)}"))

    attachment_step = _attachment_trace(list(attachments or []))
    if attachment_step:
        trace.append(attachment_step)

    return InspirationAgentResult(
        product_context=product_context,
        sources=sources,
        agent_trace=trace,
    )
