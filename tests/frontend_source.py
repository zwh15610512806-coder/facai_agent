"""Helpers for source-level frontend contract tests.

The production templates intentionally reference page-specific static assets.
Source-level tests use this helper to inspect the effective HTML/CSS/JavaScript
bundle without requiring those assets to be duplicated inline.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

_PAGE_ASSETS = {
    "api_connections.html": (
        "static/css/api-connections.css",
        "static/js/api-connections.js",
    ),
    "operations.html": (
        "static/css/api-connections.css",
        "static/js/operations.js",
    ),
    "inspiration.html": ("static/css/inspiration.css", "static/js/inspiration.js"),
    "templates.html": ("static/css/templates-library.css", "static/js/templates-library.js"),
    "search.html": ("static/css/search.css", "static/js/search.js"),
}


def read_page_source(name: str) -> str:
    """Return template markup plus the page-specific asset source it loads."""
    source = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
    css_path, js_path = _PAGE_ASSETS[name]
    css = (ROOT / css_path).read_text(encoding="utf-8-sig")
    js = (ROOT / js_path).read_text(encoding="utf-8-sig")
    return f"{source}\n<style>\n{css}\n</style>\n<script>\n{js}\n</script>\n"
