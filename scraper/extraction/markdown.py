"""Markdown Pipeline Engine (§35 Fit Markdown & Content Sanitization)."""

import re
from typing import Tuple
import markdownify
from selectolax.parser import HTMLParser


def _clean_dom_tree(parser: HTMLParser) -> None:
    """Strip navigation, header/footer boilerplate, sidebars, popups, and script/style tags."""
    selectors = [
        "nav", "header", "footer", "aside", "sidebar", "script", "style", "noscript",
        "iframe", "form", ".nav", ".navbar", ".header", ".footer", ".sidebar",
        ".cookie", ".banner", ".ad", ".ads", ".social", ".share", ".comments",
        ".login", ".auth", ".tags-box", ".top-tags"
    ]
    for tag in parser.css(", ".join(selectors)):
        tag.decompose()


def _sanitize_markdown(text: str) -> str:
    """Normalize whitespace, collapse multiple blank lines, and format clean headings."""
    if not text:
        return ""

    # Replace non-breaking spaces
    text = text.replace("\u00a0", " ")

    # Strip trailing whitespace on each line
    lines = [line.strip() for line in text.splitlines()]

    # Collapse 3+ empty lines down to a single empty line
    cleaned_lines = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
        else:
            blank_count = 0
            cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    return result


def process_markdown_pipeline(raw_html: str) -> Tuple[str, str, str]:
    """Generates (raw_markdown, clean_markdown, fit_markdown) from HTML (§35)."""
    if not raw_html:
        return "", "", ""

    # 1. Raw Markdown (Full HTML conversion with basic tag stripping)
    raw_markdown = markdownify.markdownify(
        raw_html,
        heading_style="ATX",
        strip=["script", "style", "noscript", "iframe"]
    )
    raw_markdown = _sanitize_markdown(raw_markdown)

    # 2. Clean Markdown (Semantic content extraction - main article/body block)
    clean_markdown = ""
    try:
        import trafilatura
        extracted_traf = trafilatura.extract(raw_html, include_links=True, include_images=False, output_format="markdown")
        if extracted_traf and len(extracted_traf.strip()) > 150:
            clean_markdown = _sanitize_markdown(extracted_traf)
    except Exception:
        pass

    if not clean_markdown:
        parser = HTMLParser(raw_html)
        main_container = parser.css_first("main, article, div.container, div.content, #content, body")
        if main_container:
            container_html = main_container.html or ""
            container_parser = HTMLParser(container_html)
            _clean_dom_tree(container_parser)
            clean_html = container_parser.html or ""
        else:
            _clean_dom_tree(parser)
            clean_html = parser.html or ""

        clean_markdown = markdownify.markdownify(
            clean_html,
            heading_style="ATX",
            strip=["script", "style", "noscript", "iframe", "form"]
        )
        clean_markdown = _sanitize_markdown(clean_markdown)

    # 3. Fit Markdown (Token-dense Markdown optimized for LLM/RAG - §35)
    # Remove orphan links, repetitive bullets, and inline menu noise
    fit_lines = []
    for line in clean_markdown.splitlines():
        # Skip lines that are just navigation buttons or standalone single-word links
        if re.match(r"^\[.*?\]\(/.*?\)$", line) and len(line) < 35:
            continue
        fit_lines.append(line)

    fit_markdown = _sanitize_markdown("\n".join(fit_lines))
    return raw_markdown, clean_markdown, fit_markdown
