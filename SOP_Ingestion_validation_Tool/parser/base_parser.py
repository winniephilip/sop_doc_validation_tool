"""Base parser interface shared by PDF and DOCX parsers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any


class BaseParser(ABC):
    # Patterns for common SOP header fields
    _VERSION_RE = re.compile(r"(?:version|rev(?:ision)?)[:\s]+([0-9]+(?:\.[0-9]+)*)", re.I)
    _DATE_RE = re.compile(
        r"(?:revision|effective|date)[:\s]+([0-3]?\d[/\-\.][0-1]?\d[/\-\.][0-9]{2,4}|[A-Za-z]+ \d{1,2},?\s*\d{4})",
        re.I,
    )
    _AUTHOR_RE = re.compile(r"(?:prepared by|author)[:\s]+([^\n\r]+)", re.I)
    _APPROVER_RE = re.compile(r"(?:approved by|approver)[:\s]+([^\n\r]+)", re.I)
    _DEPT_RE = re.compile(r"(?:department|dept)[:\s]+([^\n\r]+)", re.I)
    _DOCID_RE = re.compile(r"(?:document\s*(?:no|number|id)|SOP[- #]+)[:\s]*([A-Z0-9][A-Z0-9\-_\.]+)", re.I)
    _WARNING_RE = re.compile(r"(?:WARNING|CAUTION|DANGER)[:\s]+([^\n]+(?:\n(?!\s*\n)[^\n]+)*)", re.I)

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    @abstractmethod
    def extract_raw_text(self) -> str:
        """Return full plain-text of the document."""

    @abstractmethod
    def extract_sections(self) -> list[dict[str, Any]]:
        """Return ordered list of section dicts matching the schema."""

    def parse(self) -> dict[str, Any]:
        """Parse the document into a schema-conformant dict."""
        raw = self.extract_raw_text()
        sections = self.extract_sections()

        doc: dict[str, Any] = {
            "document_id": self._find(self._DOCID_RE, raw) or self.file_path.stem,
            "title": self._extract_title(raw),
            "version": self._find(self._VERSION_RE, raw) or "1.0",
            "revision_date": self._find(self._DATE_RE, raw),
            "effective_date": None,
            "department": self._find(self._DEPT_RE, raw),
            "author": self._find(self._AUTHOR_RE, raw),
            "approver": self._find(self._APPROVER_RE, raw),
            "purpose": self._extract_section_content(sections, "purpose"),
            "scope": self._extract_section_content(sections, "scope"),
            "sections": sections,
            "warnings": self._extract_warnings(raw),
            "references": self._extract_references(sections, raw),
            "revisions": [],
            "metadata": {
                "source_file": self.file_path.name,
                "file_type": self.file_path.suffix.lstrip(".").lower(),
                "parsed_at": datetime.utcnow().isoformat() + "Z",
                "page_count": None,
                "word_count": len(raw.split()),
            },
        }
        return doc

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _find(pattern: re.Pattern, text: str) -> str | None:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_title(text: str) -> str:
        for line in text.splitlines():
            line = line.strip()
            if len(line) > 5 and not line.startswith("#") and not re.match(r"^[0-9]", line):
                return line[:200]
        return "Untitled SOP"

    @staticmethod
    def _extract_section_content(sections: list[dict], keyword: str) -> str | None:
        for s in sections:
            if keyword.lower() in s["title"].lower():
                return s["content"][:1000]
        return None

    @staticmethod
    def _extract_references(sections: list[dict], raw: str) -> list[str]:
        refs: list[str] = []
        for s in sections:
            if "reference" in s["title"].lower():
                for line in s["content"].splitlines():
                    line = line.strip()
                    if line and len(line) > 3:
                        refs.append(line)
        if not refs:
            for m in re.finditer(r"(?:per|see|ref(?:erence)?)[:\s]+([A-Z][A-Z0-9 \-]+)", raw):
                refs.append(m.group(1).strip())
        return list(dict.fromkeys(refs))[:20]

    @staticmethod
    def _extract_warnings(raw: str) -> list[str]:
        warnings: list[str] = []
        for m in re.finditer(
            r"(?:WARNING|CAUTION|DANGER)[:\s]+([^\n]+(?:\n(?!\s*\n)[^\n]+){0,3})", raw
        ):
            warnings.append(m.group(0).strip()[:500])
        return list(dict.fromkeys(warnings))[:20]
