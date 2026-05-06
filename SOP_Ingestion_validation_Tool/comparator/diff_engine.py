"""Field-level + fuzzy-text comparison engine for two parsed SOP JSON dicts."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Status = Literal["MATCH", "MISMATCH", "MISSING", "ADDED"]


@dataclass
class FieldResult:
    field: str
    status: Status
    original_value: Any
    new_value: Any
    similarity: float | None = None   # 0-1 for text fields
    diff_lines: list[str] = field(default_factory=list)


@dataclass
class SectionResult:
    section_id: str
    title: str
    status: Status
    original_content: str | None
    new_content: str | None
    similarity: float | None = None
    diff_lines: list[str] = field(default_factory=list)


@dataclass
class ComparisonReport:
    original_file: str
    new_file: str
    overall_status: Status
    score: float                          # 0-1
    field_results: list[FieldResult]
    section_results: list[SectionResult]
    warnings_result: FieldResult | None
    summary: dict[str, int]               # counts per status


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Top-level fields to compare directly
SCALAR_FIELDS = [
    "title", "version", "revision_date", "effective_date",
    "department", "author", "approver", "purpose", "scope",
]

# Similarity threshold below which a text field is MISMATCH
TEXT_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DiffEngine:
    def compare(self, original: dict[str, Any], new: dict[str, Any]) -> ComparisonReport:
        field_results: list[FieldResult] = []
        section_results: list[SectionResult] = []

        # Scalar fields
        for f in SCALAR_FIELDS:
            field_results.append(self._compare_scalar(f, original.get(f), new.get(f)))

        # Sections
        section_results = self._compare_sections(
            original.get("sections", []), new.get("sections", [])
        )

        # Warnings (as a single blob comparison)
        warnings_result = self._compare_list_field(
            "warnings", original.get("warnings", []), new.get("warnings", [])
        )

        # Aggregate
        all_statuses = (
            [r.status for r in field_results]
            + [r.status for r in section_results]
            + ([warnings_result.status] if warnings_result else [])
        )
        summary = {s: all_statuses.count(s) for s in ("MATCH", "MISMATCH", "MISSING", "ADDED")}
        total = len(all_statuses) or 1
        score = summary["MATCH"] / total
        overall = "MATCH" if score == 1.0 else ("MISMATCH" if summary["MISMATCH"] > 0 else "MISMATCH")

        return ComparisonReport(
            original_file=original.get("metadata", {}).get("source_file", "original"),
            new_file=new.get("metadata", {}).get("source_file", "new"),
            overall_status=overall,
            score=round(score, 4),
            field_results=field_results,
            section_results=section_results,
            warnings_result=warnings_result,
            summary=summary,
        )

    # ── scalar ──────────────────────────────────────────────────────────────

    def _compare_scalar(self, fname: str, orig: Any, new: Any) -> FieldResult:
        if orig is None and new is None:
            return FieldResult(fname, "MATCH", orig, new)
        if orig is None:
            return FieldResult(fname, "ADDED", orig, new)
        if new is None:
            return FieldResult(fname, "MISSING", orig, new)

        # Normalise strings
        if isinstance(orig, str) and isinstance(new, str):
            similarity = self._similarity(orig, new)
            status: Status = "MATCH" if similarity >= TEXT_THRESHOLD else "MISMATCH"
            diff = self._inline_diff(orig, new) if status == "MISMATCH" else []
            return FieldResult(fname, status, orig, new, similarity, diff)

        status = "MATCH" if orig == new else "MISMATCH"
        return FieldResult(fname, status, orig, new)

    # ── list field ───────────────────────────────────────────────────────────

    def _compare_list_field(self, fname: str, orig: list, new: list) -> FieldResult:
        orig_str = "\n".join(orig)
        new_str = "\n".join(new)
        similarity = self._similarity(orig_str, new_str) if orig_str or new_str else 1.0
        status: Status = "MATCH" if similarity >= TEXT_THRESHOLD else "MISMATCH"
        if not orig and not new:
            status = "MATCH"
        diff = self._inline_diff(orig_str, new_str) if status == "MISMATCH" else []
        return FieldResult(fname, status, orig, new, similarity, diff)

    # ── sections ─────────────────────────────────────────────────────────────

    def _compare_sections(
        self, orig_sections: list[dict], new_sections: list[dict]
    ) -> list[SectionResult]:
        orig_map = {self._norm_title(s["title"]): s for s in orig_sections}
        new_map  = {self._norm_title(s["title"]): s for s in new_sections}

        results:       list[SectionResult] = []
        matched_orig:  set[str] = set()
        matched_new:   set[str] = set()

        # ── pass 1: title-key matches ─────────────────────────────────────────
        for key in dict.fromkeys(list(orig_map) + list(new_map)):
            o = orig_map.get(key)
            n = new_map.get(key)
            if o and n:
                matched_orig.add(key)
                matched_new.add(key)
                o_c = o["content"]
                n_c = n["content"]
                sim = self._similarity(o_c, n_c)
                status: Status = "MATCH" if sim >= TEXT_THRESHOLD else "MISMATCH"
                diff = self._inline_diff(o_c, n_c) if status == "MISMATCH" else []
                results.append(SectionResult(o["section_id"], o["title"], status, o_c, n_c, sim, diff))

        unmatched_orig = [s for k, s in orig_map.items() if k not in matched_orig]
        unmatched_new  = [s for k, s in new_map.items()  if k not in matched_new]

        # ── pass 2: content-similarity fallback for title-mismatched sections ─
        CONTENT_MATCH_THRESHOLD = 0.40   # low threshold — titles differ, content should align
        pairs: list[tuple[float, dict, dict]] = []
        for o in unmatched_orig:
            for n in unmatched_new:
                if o["content"] or n["content"]:
                    sim = self._similarity(o["content"], n["content"])
                    if sim >= CONTENT_MATCH_THRESHOLD:
                        pairs.append((sim, o, n))

        pairs.sort(key=lambda x: x[0], reverse=True)
        used_orig: set[str] = set()
        used_new:  set[str] = set()
        for sim, o, n in pairs:
            if o["section_id"] in used_orig or n["section_id"] in used_new:
                continue
            used_orig.add(o["section_id"])
            used_new.add(n["section_id"])
            status = "MATCH" if sim >= TEXT_THRESHOLD else "MISMATCH"
            diff = self._inline_diff(o["content"], n["content"]) if status == "MISMATCH" else []
            results.append(SectionResult(o["section_id"], o["title"], status, o["content"], n["content"], sim, diff))

        # ── pass 3: remaining unmatched → MISSING / ADDED ─────────────────────
        for o in unmatched_orig:
            if o["section_id"] not in used_orig:
                results.append(SectionResult(o["section_id"], o["title"], "MISSING", o["content"], None))
        for n in unmatched_new:
            if n["section_id"] not in used_new:
                results.append(SectionResult(n["section_id"], n["title"], "ADDED", None, n["content"]))

        results.sort(key=lambda r: r.section_id)
        return results

    # ── text similarity ───────────────────────────────────────────────────────

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        if not a and not b:
            return 1.0
        a_norm = re.sub(r"\s+", " ", a.lower().strip())
        b_norm = re.sub(r"\s+", " ", b.lower().strip())
        return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()

    @staticmethod
    def _inline_diff(a: str, b: str) -> list[str]:
        a_lines = a.splitlines(keepends=True)
        b_lines = b.splitlines(keepends=True)
        return list(difflib.unified_diff(a_lines, b_lines, lineterm="", n=2))[:60]

    @staticmethod
    def _norm_title(t: str) -> str:
        # Strip leading numeric order prefix: "1.", "1.2.", "2.3.1 ", etc.
        t = re.sub(r"^\d+(\.\d+)*\.?\s*", "", t.strip())
        return re.sub(r"[^a-z0-9]", "", t.lower())
