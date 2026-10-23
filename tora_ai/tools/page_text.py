"""Turn an HTML page into clean, model-readable text.

Adapted from gpt-oss (gpt_oss/tools/simple_browser/page_contents.py, Apache 2.0, (c) OpenAI).
Changes: links become a numbered list instead of harmony-style 【id†text】 anchors, scripts and
page chrome are stripped, and the tiktoken/aiohttp-specific parts were removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import html2text
import lxml.etree
import lxml.html

HTML_SUP_RE = re.compile(r"<sup( [^>]*)?>([\w\-]+)</sup>")
HTML_SUB_RE = re.compile(r"<sub( [^>]*)?>([\w\-]+)</sub>")
HTML_TAGS_SEQ_RE = re.compile(r"(?<=\w)((<[^>]*>)+)(?=\w)")
EMPTY_LINE_RE = re.compile(r"^\s+$", flags=re.MULTILINE)
EXTRA_NEWLINE_RE = re.compile(r"\n(\s*\n)+")
SMP_RE = re.compile(r"[\U00010000-\U0001FFFF]")  # lxml.html can't handle these characters
NOISE_TAGS = ("script", "style", "noscript", "svg", "math", "iframe", "form", "nav", "footer")


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (link text, absolute URL)


def _merge_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def _replace_node_with_text(node: lxml.html.HtmlElement, text: str) -> None:
    # Replace a node with plain text while keeping the text around it.
    previous, parent, tail = node.getprevious(), node.getparent(), node.tail or ""
    if previous is None:
        parent.text = (parent.text or "") + text + tail
    else:
        previous.tail = (previous.tail or "") + text + tail
    parent.remove(node)


def _collect_links(root: lxml.html.HtmlElement, base_url: str, limit: int) -> list[tuple[str, str]]:
    links, seen = [], set()
    for a in root.findall(".//a[@href]"):
        href = a.attrib["href"]
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        url = urljoin(base_url, href)
        text = _merge_whitespace(" ".join(a.itertext()))
        if not text or not urlparse(url).netloc or url in seen:
            continue
        seen.add(url)
        links.append((text[:80], url))
        if len(links) >= limit:
            break
    return links


def html_to_text(html: str) -> str:
    """Convert an HTML string to clean plain text."""
    html = re.sub(HTML_SUP_RE, r"^{\2}", html)
    html = re.sub(HTML_SUB_RE, r"_{\2}", html)
    html = re.sub(HTML_TAGS_SEQ_RE, r" \1", html)  # keep words in adjacent cells apart
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    h.unicode_snob = True
    h.body_width = 0  # no wrapping
    text = h.handle(html).strip()
    text = re.sub(EMPTY_LINE_RE, "", text)
    return re.sub(EXTRA_NEWLINE_RE, "\n\n", text)


def process_html(html: str, url: str = "", max_links: int = 40) -> Page:
    """Parse a page into its title, readable text and outgoing links."""
    root = lxml.html.fromstring(SMP_RE.sub("", html.replace("​", "")) or "<html></html>")
    title_el = root.find(".//title")
    title = _merge_whitespace(title_el.text_content()) if title_el is not None else urlparse(url).netloc
    # Prefer the page's main content area when it marks one, to skip menus and sidebars.
    for candidate in (root.find(".//main"), root.find(".//article"), next(iter(root.xpath("//*[@role='main']")), None)):
        if candidate is not None:
            root = candidate
            break
    for tag in NOISE_TAGS:
        for node in root.findall(f".//{tag}"):
            node.getparent().remove(node)
    links = _collect_links(root, url, max_links)
    for i, img in enumerate(root.findall(".//img")):
        name = img.get("alt") or img.get("title")
        _replace_node_with_text(img, f"[Image {i}: {name}]" if name else f"[Image {i}]")
    text = html_to_text(lxml.etree.tostring(root, encoding="UTF-8").decode())
    return Page(url=url, title=title, text=text, links=links)
