"""Small web-search helper for Inspiration research modes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree
import logging
import re

import httpx


logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 FacaiAgent/1.0",
}


def _strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


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
    for item in soup.select(".result, .web-result"):
        title_node = (
            item.select_one(".result__a")
            or item.select_one("a.result-link")
            or item.select_one("h2 a")
            or item.select_one("a[href]")
        )
        snippet_node = item.select_one(".result__snippet") or item.select_one(".result-snippet")
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


def _parse_bing_rss(xml_text: str, max_results: int) -> list[WebSearchResult]:
    try:
        root = ElementTree.fromstring(xml_text or "")
    except ElementTree.ParseError:
        return []

    results: list[WebSearchResult] = []
    for item in root.findall(".//item"):
        title = _strip_markup(item.findtext("title") or "")
        url = _clean_url((item.findtext("link") or "").strip())
        snippet = _strip_markup(item.findtext("description") or "")
        if title and url:
            results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        if len(results) >= max_results:
            break
    return results


def _unique_results(results: list[WebSearchResult], max_results: int) -> list[WebSearchResult]:
    unique: list[WebSearchResult] = []
    seen: set[str] = set()
    for result in results:
        key = (result.url or result.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(result)
        if len(unique) >= max_results:
            break
    return unique


def _filter_relevant_results(results: list[WebSearchResult], query: str) -> list[WebSearchResult]:
    query_text = (query or "").lower()
    if "法采" not in query_text and "facai" not in query_text:
        return results

    filtered = []
    for result in results:
        haystack = f"{result.title} {result.url} {result.snippet}".lower()
        if "法采" in haystack or "facai" in haystack:
            filtered.append(result)
    return filtered


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []
    max_results = max(1, min(max_results, 8))
    results: list[WebSearchResult] = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        try:
            response = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers=SEARCH_HEADERS,
            )
            response.raise_for_status()
            results = _parse_duckduckgo_html(response.text, max_results)
        except Exception as exc:
            logger.warning("DuckDuckGo web research search failed: %s", exc)

        if not results:
            try:
                response = await client.get(
                    "https://www.bing.com/search",
                    params={"q": query, "format": "rss"},
                    headers=SEARCH_HEADERS,
                )
                response.raise_for_status()
                results = _parse_bing_rss(response.text, max_results)
            except Exception as exc:
                logger.warning("Bing RSS web research search failed: %s", exc)

    unique_results = _unique_results(results, max_results)
    relevant_results = _filter_relevant_results(unique_results, query)
    return [asdict(item) for item in relevant_results[:max_results]]
