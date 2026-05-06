"""Extract text from a screenshot image via OCR and convert to a SOP-schema dict."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

# ── Tesseract path — Windows auto-detection ───────────────────────────────────
# The installer adds tesseract to PATH, but the running server process may not
# have picked up that change. Probe the two standard install locations.
def _configure_tesseract_windows() -> None:
    import os
    import pytesseract
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(
            os.environ.get("USERNAME", "")
        ),
    ]
    # Also check PATH — maybe the server did pick it up
    import shutil
    if shutil.which("tesseract"):
        return  # already on PATH, no override needed
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return

if sys.platform == "win32":
    try:
        _configure_tesseract_windows()
    except Exception:
        pass  # fail silently; the actual call will surface the error


# ── OCR backend ───────────────────────────────────────────────────────────────

def _try_pytesseract(img: Image.Image) -> str:
    import pytesseract
    return pytesseract.image_to_string(img, config="--psm 6 --oem 3")

def _try_easyocr(img: Image.Image) -> str:
    import easyocr
    import numpy as np
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    result = reader.readtext(np.array(img), detail=0, paragraph=True)
    return "\n".join(result)

def _extract_text(img: Image.Image) -> str:
    try:
        return _try_pytesseract(img)
    except Exception as e:
        err_lower = str(e).lower()
        if any(kw in err_lower for kw in ("tesseract is not installed", "not found",
                                           "no such file", "cannot find", "filenotfounderror")):
            try:
                return _try_easyocr(img)
            except ImportError:
                raise RuntimeError(
                    "Tesseract OCR binary not found. "
                    "Download from https://github.com/UB-Mannheim/tesseract/wiki "
                    "and ensure it is installed to C:\\Program Files\\Tesseract-OCR\\."
                ) from e
        raise RuntimeError(f"OCR failed: {e}") from e


# ── Public API ────────────────────────────────────────────────────────────────

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def ocr_image(file_path: str | Path) -> dict[str, Any]:
    """Open *file_path*, OCR it, and return a schema-conformant SOP dict."""
    path = Path(file_path)
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported image format: {path.suffix}")

    img = Image.open(path)
    img = _preprocess(img)
    raw_text = _extract_text(img)

    if not raw_text.strip():
        raise ValueError("No text could be extracted from the image. "
                         "Try a higher-resolution screenshot.")

    return _text_to_sop(raw_text, source_file=path.name)


def ocr_bytes(data: bytes, filename: str) -> dict[str, Any]:
    """OCR raw image bytes (used by the API route)."""
    import io
    img = Image.open(io.BytesIO(data))
    img = _preprocess(img)
    raw_text = _extract_text(img)

    if not raw_text.strip():
        raise ValueError("No text could be extracted from the image. "
                         "Try a higher-resolution screenshot.")

    return _text_to_sop(raw_text, source_file=filename)


# ── Image preprocessing ───────────────────────────────────────────────────────

def _preprocess(img: Image.Image) -> Image.Image:
    """Convert to greyscale, upscale small images, sharpen edges."""
    img = img.convert("L")                        # greyscale

    # Upscale if narrow — Tesseract struggles below ~150 dpi equivalent
    w, h = img.size
    if w < 1200:
        scale = max(2, 1200 // w)
        img = img.resize((w * scale, h * scale), Image.LANCZOS)

    img = ImageOps.autocontrast(img)              # normalise brightness
    img = img.filter(ImageFilter.SHARPEN)
    return img


# ── Text → SOP schema ─────────────────────────────────────────────────────────

_VERSION_RE   = re.compile(r"(?:version|rev(?:ision)?)[:\s]+([0-9]+(?:\.[0-9]+)*)", re.I)
_DATE_RE      = re.compile(r"(?:revision|effective|date)[:\s]+([0-3]?\d[/\-\.][0-1]?\d[/\-\.][0-9]{2,4})", re.I)
_AUTHOR_RE    = re.compile(r"(?:prepared by|author)[:\s]+([^\n\r]{2,80})", re.I)
_APPROVER_RE  = re.compile(r"(?:approved by|approver)[:\s]+([^\n\r]{2,80})", re.I)
_DEPT_RE      = re.compile(r"(?:department|dept)[:\s]+([^\n\r]{2,80})", re.I)
_HEADING_RE   = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+([A-Z][^\n]{2,80})$|^([A-Z][A-Z\s]{3,60})$", re.M)
_WARNING_RE   = re.compile(r"(?:WARNING|CAUTION|DANGER)[:\s]+([^\n]+(?:\n(?!\s*\n)[^\n]+){0,3})", re.I)


def _find(pat: re.Pattern, text: str) -> str | None:
    m = pat.search(text)
    return m.group(1).strip() if m else None


def _text_to_sop(raw: str, source_file: str = "") -> dict[str, Any]:
    sections = _split_sections(raw)
    purpose  = next((s["content"] for s in sections if "purpose" in s["title"].lower()), None)
    scope    = next((s["content"] for s in sections if "scope"   in s["title"].lower()), None)

    warnings: list[str] = []
    for m in _WARNING_RE.finditer(raw):
        warnings.append(m.group(0).strip()[:500])

    title = _detect_title(raw)

    return {
        "document_id":    source_file,
        "title":          title,
        "version":        _find(_VERSION_RE, raw),
        "revision_date":  _find(_DATE_RE, raw),
        "effective_date": None,
        "department":     _find(_DEPT_RE, raw),
        "author":         _find(_AUTHOR_RE, raw),
        "approver":       _find(_APPROVER_RE, raw),
        "purpose":        purpose,
        "scope":          scope,
        "sections":       sections,
        "warnings":       list(dict.fromkeys(warnings))[:20],
        "references":     [],
        "revisions":      [],
        "metadata": {
            "source_file": source_file,
            "file_type":   "screenshot",
            "parsed_at":   datetime.utcnow().isoformat() + "Z",
            "page_count":  1,
            "word_count":  len(raw.split()),
            "raw_ocr_text": raw[:5000],    # kept for debugging
        },
    }


def _detect_title(raw: str) -> str:
    for line in raw.splitlines():
        line = line.strip()
        if len(line) > 5 and not re.match(r"^[0-9]", line):
            return line[:200]
    return "Untitled SOP"


def _split_sections(raw: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    order = 0

    for line in raw.splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            if current:
                current["content"] = current["content"].strip()
                sections.append(current)
            num   = (m.group(1) or "").rstrip(".")
            title = (m.group(2) or m.group(3) or "").strip()
            order += 1
            current = {
                "section_id": num or f"s{order}",
                "title":      title,
                "content":    "",
                "order":      order,
                "subsections": [],
            }
        elif current is not None:
            current["content"] += line + "\n"

    if current:
        current["content"] = current["content"].strip()
        sections.append(current)

    # Fallback: paragraph split when no headings detected
    if not sections:
        paras = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
        for i, para in enumerate(paras[:50], 1):
            sections.append({
                "section_id": f"p{i}",
                "title":      para.splitlines()[0][:80],
                "content":    para,
                "order":      i,
                "subsections": [],
            })

    return sections
