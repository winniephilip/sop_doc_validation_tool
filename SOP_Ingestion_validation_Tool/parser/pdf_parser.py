"""PDF → JSON parser using pdfplumber."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from .base_parser import BaseParser


_HEADING_RE = re.compile(
    r"^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,80})$|^([A-Z][A-Z\s]{3,60})$"
)


class PdfParser(BaseParser):
    def __init__(self, file_path: str | Path) -> None:
        super().__init__(file_path)
        self._pages: list[str] = []

    # ── raw text ───────────────────────────────────────────────────────────────

    def extract_raw_text(self) -> str:
        if self._pages:
            return "\n".join(self._pages)
        with pdfplumber.open(self.file_path) as pdf:
            self._page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                self._pages.append(text)
        return "\n".join(self._pages)

    # ── sections ──────────────────────────────────────────────────────────────

    def extract_sections(self) -> list[dict[str, Any]]:
        raw = self.extract_raw_text()
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        order = 0

        for line in raw.splitlines():
            m = _HEADING_RE.match(line.strip())
            if m:
                if current:
                    current["content"] = current["content"].strip()
                    sections.append(current)
                num = m.group(1) or ""
                title = (m.group(2) or m.group(3) or "").strip()
                order += 1
                current = {
                    "section_id": num or f"s{order}",
                    "title": title,
                    "content": "",
                    "order": order,
                    "subsections": [],
                }
            elif current is not None:
                current["content"] += line + "\n"

        if current:
            current["content"] = current["content"].strip()
            sections.append(current)

        if not sections:
            sections = self._fallback_sections(raw)

        return sections

    # ── override parse to inject page count ───────────────────────────────────

    def parse(self) -> dict[str, Any]:
        doc = super().parse()
        doc["metadata"]["page_count"] = getattr(self, "_page_count", None)
        return doc

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_sections(raw: str) -> list[dict[str, Any]]:
        """Split on blank-line boundaries when no headings are detected."""
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
        sections: list[dict[str, Any]] = []
        for i, para in enumerate(paragraphs[:50], 1):
            first_line = para.splitlines()[0][:80]
            sections.append(
                {
                    "section_id": f"p{i}",
                    "title": first_line,
                    "content": para,
                    "order": i,
                    "subsections": [],
                }
            )
        return sections
