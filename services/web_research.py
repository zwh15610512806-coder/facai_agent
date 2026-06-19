"""Small web-search helper for Inspiration research modes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlparse
import logging

import httpx


logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


def _clean_url(url: str) -> str:
    url = url or ""
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.query:
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    return url


def _parse_duckduckgo_html(html: str, max_results: int) -> list[WebSearchResult]:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        logger.warning("BeautifulSoup unavailable; web research parsing skipped")
        return []

    soup = BeautifulSoup(html or "", "html.parser")
    results: list[WebSearchResult] = []
    for item in soup.select(".result"):
        title_node = item.select_one(".result__a")
        snippet_node = item.select_one(".result__snippet")
        if not title_node:
            continue
        title = title_node.get_text(" ", strip=True)
        url = _clean_url(title_node.get("href") or "")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        if title and url:
            results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        if len(results) >= max_results:
            break
    return results


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []
    max_results = max(1, min(max_results, 8))
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 FacaiAgent/1.0"},
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Web research search failed: %s", exc)
        return []
    return [asdict(item) for item in _parse_duckduckgo_html(response.text, max_results)]
