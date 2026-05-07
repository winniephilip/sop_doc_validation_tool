"""Scrape a URL and convert its content into a pseudo-SOP dict for comparison."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag


def scrape_webpage(url: str, timeout: int = 20) -> dict[str, Any]:
    """Fetch *url*, parse HTML, and return a schema-conformant SOP dict."""
    resp = httpx.get(url, timeout=timeout, follow_redirects=True,
                     headers={"User-Agent": "SOP-Validation-Tool/1.0"})
    resp.raise_for_status()
    return html_to_sop(resp.text, source_url=url)


def html_to_sop(html: str, source_url: str = "") -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise tags from the full document first
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "noscript", "button", "form"]):
        tag.decompose()

    # Scope to crew-rendered-content if present; fall back to full document
    content_root = soup.find("div", class_="crew-rendered-content") or soup

    title    = _page_title(soup, content_root)
    meta     = _meta_fields(content_root)
    sections = _extract_sections(content_root)
    raw_text = " ".join(s["content"] for s in sections)

    return {
        "document_id":    meta.get("document_id") or source_url,
        "title":          title,
        "version":        meta.get("version"),
        "revision_date":  meta.get("revision_date"),
        "effective_date": None,
        "department":     meta.get("department"),
        "author":         meta.get("author"),
        "approver":       meta.get("approver"),
        "purpose":        _section_content(sections, "purpose"),
        "scope":          _section_content(sections, "scope"),
        "sections":       sections,
        "warnings":       _extract_warnings(raw_text),
        "references":     _extract_references(content_root),
        "revisions":      [],
        "metadata": {
            "source_file":    source_url,
            "file_type":      "webpage",
            "parsed_at":      datetime.utcnow().isoformat() + "Z",
            "page_count":     None,
            "word_count":     len(raw_text.split()),
            "scoped_to":      "div.crew-rendered-content"
                              if soup.find("div", class_="crew-rendered-content")
                              else "full-document",
        },
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _page_title(soup: BeautifulSoup, root: Any) -> str:
    crew_title = root.find("div", class_="crew-header-title")
    if crew_title and crew_title.get_text(strip=True):
        return crew_title.get_text(strip=True)[:200]
    h1 = root.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:200]
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)[:200]
    return "Untitled Page"


def _meta_fields(root: Any) -> dict[str, str | None]:
    """Scan the scoped root for version, author, date, etc."""
    result: dict[str, str | None] = {}

    # CREW-specific: structured extraction from crew-header-meta spans
    meta_div = root.find("div", class_="crew-header-meta")
    if meta_div:
        spans = [s.get_text(strip=True) for s in meta_div.find_all("span") if s.get_text(strip=True)]
        if spans:
            result["document_id"] = spans[0]   # e.g. "01.06.00.01-01g"
        if len(spans) > 1:
            rev_m = re.search(r"(?:revision|rev)[:\s]+([0-9]+(?:\.[0-9]+)*)", spans[1], re.I)
            if rev_m:
                result["version"] = rev_m.group(1)

    # Regex fallback on full body text (does not overwrite CREW-specific values)
    full_text = root.get_text(separator="\n")
    patterns = {
        "version":       re.compile(r"(?:version|rev(?:ision)?)[:\s]+([0-9]+(?:\.[0-9]+)*)", re.I),
        "revision_date": re.compile(r"(?:revision|effective|date)[:\s]+([0-3]?\d[/\-\.][0-1]?\d[/\-\.][0-9]{2,4})", re.I),
        "author":        re.compile(r"(?:prepared by|author)[:\s]+([^\n\r]{2,80})", re.I),
        "approver":      re.compile(r"(?:approved by|approver)[:\s]+([^\n\r]{2,80})", re.I),
        "department":    re.compile(r"(?:department|dept)[:\s]+([^\n\r]{2,80})", re.I),
    }
    for key, pat in patterns.items():
        if key not in result:
            m = pat.search(full_text)
            result[key] = m.group(1).strip() if m else None
    return result


def _is_section_heading(node: Tag) -> bool:
    """Return True if this element acts as a section heading."""
    tag = (node.name or "").lower()
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return True
    # CREW-style: <div class="crew-section">
    if tag == "div" and "crew-section" in (node.get("class") or []):
        return True
    return False


def _extract_sections(root: Any) -> list[dict[str, Any]]:
    """
    Extract sections from *root*.

    Strategy:
    1. If a CREW-style `div.crew-document` container is found, walk its
       direct children — `div.crew-section` and heading tags mark section
       boundaries; every other child contributes its full text as content.
    2. Otherwise fall back to a descendants walk that looks for h1-h6.
    """
    # ── CREW structured document ──────────────────────────────────────────────
    container = root.find("div", class_="crew-document")
    if container:
        return _extract_sections_crew(container)

    # ── Standard HTML fallback ────────────────────────────────────────────────
    return _extract_sections_standard(root)


def _extract_crew_header(card: Tag) -> dict[str, Any] | None:
    """Build a comparable section from div.crew-header-card content."""
    parts: list[str] = []

    logo = card.find("div", class_="crew-header-logo")
    if logo:
        txt = logo.get_text(strip=True)
        if txt:
            parts.append(txt)

    title_div = card.find("div", class_="crew-header-title")
    if title_div:
        txt = title_div.get_text(strip=True)
        if txt:
            parts.append(txt)

    meta = card.find("div", class_="crew-header-meta")
    if meta:
        for span in meta.find_all("span"):
            txt = span.get_text(strip=True)
            if txt:
                parts.append(txt)

    if not parts:
        return None

    return {
        "section_id":  "crew-header",
        "title":       "Header",
        "content":     "\n".join(parts),
        "order":       0,
        "subsections": [],
    }


def _extract_sections_crew(container: Any) -> list[dict[str, Any]]:
    """Walk direct children of a crew-document div."""
    SKIP_TAGS = {"style", "script"}

    sections: list[dict[str, Any]] = []
    order = 0
    current: dict[str, Any] | None = None

    # Extract header card as the first section before the main walk
    header_card = container.find("div", class_="crew-header-card")
    if header_card:
        header_sec = _extract_crew_header(header_card)
        if header_sec:
            order += 1
            header_sec["order"] = order
            sections.append(header_sec)

    def flush():
        nonlocal current, order
        if current is None:
            return
        current["content"] = current["content"].strip()
        order += 1
        current["order"] = order
        sections.append(current)
        current = None

    for child in container.children:
        if not isinstance(child, Tag) or not child.name:
            continue
        tag = child.name.lower()
        classes = set(child.get("class") or [])

        if tag in SKIP_TAGS or "crew-header-card" in classes:
            continue  # header already extracted above

        if _is_section_heading(child):
            flush()
            title = child.get_text(separator=" ", strip=True)[:200]
            sid   = child.get("id", "").strip() or re.sub(r"[^a-z0-9]", "-", title.lower())[:40]
            current = {
                "section_id":  sid,
                "title":       title,
                "content":     "",
                "order":       0,
                "subsections": [],
            }
        else:
            # Any non-heading child: grab full text (captures nested li, p, td…)
            txt = child.get_text(separator="\n", strip=True)
            if not txt:
                continue
            if current is not None:
                current["content"] += txt + "\n"
            else:
                # Content before the first heading — create an implicit preamble section
                order += 1
                sections.append({
                    "section_id":  f"preamble-{order}",
                    "title":       txt.splitlines()[0][:80],
                    "content":     txt,
                    "order":       order,
                    "subsections": [],
                })

    flush()
    return sections


def _extract_sections_standard(root: Any) -> list[dict[str, Any]]:
    """Descendants walk for standard HTML with h1-h6 headings."""
    sections: list[dict[str, Any]] = []
    order = 0
    current_title: str | None = None
    current_id: str = ""
    current_content: list[str] = []

    def flush():
        nonlocal current_title, current_id, current_content, order
        if current_title is None:
            return
        order += 1
        sections.append({
            "section_id":  current_id or f"s{order}",
            "title":       current_title,
            "content":     "\n".join(current_content).strip(),
            "order":       order,
            "subsections": [],
        })
        current_title = None
        current_id = ""
        current_content = []

    for node in root.descendants:
        if not isinstance(node, Tag):
            continue
        tag = (node.name or "").lower()

        if _is_section_heading(node):
            flush()
            current_title = node.get_text(separator=" ", strip=True)[:200]
            current_id    = node.get("id", "").strip() or \
                            re.sub(r"[^a-z0-9]", "-", current_title.lower())[:40]

        elif tag in {"p", "li", "td", "dd"} and current_title is not None:
            txt = node.get_text(separator=" ", strip=True)
            if txt:
                current_content.append(txt)

    flush()

    if not sections:
        raw   = root.get_text(separator="\n")
        paras = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
        for i, para in enumerate(paras[:50], 1):
            sections.append({
                "section_id":  f"p{i}",
                "title":       para.splitlines()[0][:80],
                "content":     para,
                "order":       i,
                "subsections": [],
            })

    return sections


def _section_content(sections: list[dict], keyword: str) -> str | None:
    for s in sections:
        if keyword.lower() in s["title"].lower():
            return s["content"][:1000]
    return None


def _extract_warnings(text: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r"(?:WARNING|CAUTION|DANGER)[:\s]+([^\n]+(?:\n(?!\s*\n)[^\n]+){0,3})", text):
        found.append(m.group(0).strip()[:500])
    return list(dict.fromkeys(found))[:20]


def _extract_references(root: Any) -> list[str]:
    refs: list[str] = []
    for a in root.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith("#") and not href.startswith("javascript"):
            text = a.get_text(strip=True)
            refs.append(f"{text} ({href})" if text else href)
    return list(dict.fromkeys(refs))[:20]
