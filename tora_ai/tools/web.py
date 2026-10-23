"""Web tools: search (Exa or You.com, needs an API key) and page fetching (no key needed).

The search API details follow gpt-oss's simple_browser backends (Apache 2.0, (c) OpenAI).
"""

from __future__ import annotations

import os

import requests

from .. import __version__
from .page_text import process_html

USER_AGENT = f"Mozilla/5.0 (compatible; tora-ai/{__version__})"
TIMEOUT = 20


class WebError(Exception):
    pass


def search_provider() -> str | None:
    """Which search API is configured, if any."""
    if os.getenv("EXA_API_KEY"):
        return "exa"
    if os.getenv("YDC_API_KEY"):
        return "youcom"
    return None


def _check(resp: requests.Response, service: str) -> dict:
    if resp.status_code != 200:
        raise WebError(f"{service} returned HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def web_search(query: str, count: int = 5) -> str:
    count = max(1, min(int(count), 10))
    provider = search_provider()
    if provider == "exa":
        data = _check(requests.post(
            "https://api.exa.ai/search",
            json={"query": query, "numResults": count, "contents": {"summary": True}},
            headers={"x-api-key": os.environ["EXA_API_KEY"], "user-agent": USER_AGENT},
            timeout=TIMEOUT,
        ), "Exa")
        results = [(r.get("title") or r["url"], r["url"], r.get("summary") or "") for r in data.get("results", [])]
    elif provider == "youcom":
        data = _check(requests.get(
            "https://ydc-index.io/v1/search",
            params={"query": query, "count": count},
            headers={"x-api-key": os.environ["YDC_API_KEY"], "user-agent": USER_AGENT},
            timeout=TIMEOUT,
        ), "You.com")
        found = data.get("results", {})
        results = [(r["title"], r["url"], " ".join(r.get("snippets") or [])) for r in found.get("web", [])]
        results += [(r["title"], r["url"], r.get("description", "")) for r in found.get("news", [])]
    else:
        raise WebError("Web search is not configured: set EXA_API_KEY or YDC_API_KEY.")
    if not results:
        return f"No results for {query!r}."
    lines = [f"Search results for {query!r}:"]
    for i, (title, url, snippet) in enumerate(results[:count], 1):
        lines.append(f"{i}. {title}\n   {url}\n   {snippet.strip()[:400]}")
    return "\n".join(lines)


def fetch_page(url: str, max_chars: int = 12000) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(url, headers={"user-agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise WebError(f"Could not fetch {url}: {e}") from e
    if resp.status_code >= 400:
        raise WebError(f"{url} returned HTTP {resp.status_code}")
    content_type = resp.headers.get("content-type", "")
    if "html" in content_type:
        page = process_html(resp.text, url=resp.url)
        title, text, links = page.title, page.text, page.links
    elif content_type.startswith("text/") or "json" in content_type:
        title, text, links = url, resp.text, []
    else:
        raise WebError(f"{url} is {content_type or 'an unknown type'}, not a readable page.")
    truncated = len(text) > max_chars
    out = [f"Title: {title}", f"URL: {resp.url}", "", text[:max_chars]]
    if truncated:
        out.append(f"\n[Page truncated: showing {max_chars:,} of {len(text):,} characters]")
    if links:
        out.append("\nLinks on this page:")
        out += [f"- {label}: {link}" for label, link in links[:25]]
    return "\n".join(out)
