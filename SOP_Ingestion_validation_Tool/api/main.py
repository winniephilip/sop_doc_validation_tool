"""FastAPI application for the SOP Ingestion Validation Tool."""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Resolve paths relative to project root
ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT / "uploads"
REPORTS_DIR = ROOT / "reports"
WEB_DIR = ROOT / "web"
SCHEMA_PATH = ROOT / "schemas" / "sop_schema.json"

UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# Lazy imports so the app starts even if libs are missing
def _get_parser():
    from parser import parse_file
    return parse_file

def _get_engine():
    from comparator import DiffEngine
    return DiffEngine()

def _scrape(url: str) -> dict[str, Any]:
    from comparator.web_scraper import scrape_webpage
    return scrape_webpage(url)

def _parse_html(html: str, source: str) -> dict[str, Any]:
    from comparator.web_scraper import html_to_sop
    return html_to_sop(html, source_url=source)

def _ocr(data: bytes, filename: str) -> dict[str, Any]:
    from comparator.image_ocr import ocr_bytes, SUPPORTED_EXTS
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise HTTPException(400, f"Unsupported image format: {ext}. Use PNG, JPG, WEBP, BMP or TIFF.")
    return ocr_bytes(data, filename)


app = FastAPI(title="SOP Ingestion Validation Tool", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the static web UI
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ── helpers ──────────────────────────────────────────────────────────────────

def _save_upload(upload: UploadFile) -> Path:
    ext = Path(upload.filename or "file").suffix.lower()
    if ext not in {".pdf", ".docx", ".doc"}:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest


def _report_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{report_id}.json"


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>SOP Validation Tool API</h1><p>See /docs for API reference.</p>")


@app.get("/ocr-status")
async def ocr_status() -> dict:
    """Check whether Tesseract OCR is reachable from the server process."""
    try:
        import pytesseract
        from comparator.image_ocr import _configure_tesseract_windows
        import sys
        if sys.platform == "win32":
            _configure_tesseract_windows()
        ver = pytesseract.get_tesseract_version()
        return {"available": True, "version": str(ver),
                "cmd": pytesseract.pytesseract.tesseract_cmd}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


@app.get("/schema")
async def get_schema() -> dict:
    """Return the JSON schema used for parsed SOP documents."""
    if not SCHEMA_PATH.exists():
        raise HTTPException(500, "Schema file not found")
    return json.loads(SCHEMA_PATH.read_text())


@app.post("/parse")
async def parse_document(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a PDF or DOCX and return its parsed JSON representation."""
    saved = _save_upload(file)
    try:
        parse_file = _get_parser()
        result = parse_file(saved)
        return result
    except Exception as exc:
        raise HTTPException(500, f"Parsing failed: {exc}") from exc
    finally:
        saved.unlink(missing_ok=True)


@app.post("/compare")
async def compare_documents(
    original: UploadFile = File(...),
    new_version: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload two documents and return a detailed comparison report."""
    orig_path = _save_upload(original)
    new_path = _save_upload(new_version)
    try:
        parse_file = _get_parser()
        orig_doc = parse_file(orig_path)
        new_doc = parse_file(new_path)

        engine = _get_engine()
        report = engine.compare(orig_doc, new_doc)

        # Persist for later retrieval
        report_id = uuid.uuid4().hex
        report_dict = _report_to_dict(report)
        report_dict["report_id"] = report_id
        report_dict["original_parsed"] = orig_doc
        report_dict["new_parsed"] = new_doc
        _report_path(report_id).write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return report_dict
    except Exception as exc:
        raise HTTPException(500, f"Comparison failed: {exc}") from exc
    finally:
        orig_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)


@app.get("/report/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    """Retrieve a previously generated comparison report by ID."""
    path = _report_path(report_id)
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/reports")
async def list_reports() -> list[dict[str, Any]]:
    """List all stored comparison reports (summary only)."""
    reports: list[dict[str, Any]] = []
    for p in sorted(REPORTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            reports.append({
                "report_id": data.get("report_id", p.stem),
                "original_file": data.get("original_file"),
                "new_file": data.get("new_file"),
                "overall_status": data.get("overall_status"),
                "score": data.get("score"),
                "summary": data.get("summary"),
            })
        except Exception:
            continue
    return reports


@app.post("/compare-screenshot")
async def compare_doc_vs_screenshot(
    document: UploadFile = File(...),
    screenshot: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload a document and a screenshot image; OCR the screenshot and compare."""
    doc_path = _save_upload(document)
    img_data = await screenshot.read()
    try:
        parse_file = _get_parser()
        doc_parsed = parse_file(doc_path)

        try:
            img_parsed = _ocr(img_data, screenshot.filename or "screenshot.png")
        except RuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        engine = _get_engine()
        report = engine.compare(doc_parsed, img_parsed)

        report_id = uuid.uuid4().hex
        report_dict = _report_to_dict(report)
        report_dict["report_id"] = report_id
        report_dict["compare_mode"] = "doc_vs_screenshot"
        report_dict["original_parsed"] = doc_parsed
        report_dict["new_parsed"] = img_parsed
        _report_path(report_id).write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return report_dict
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Comparison failed: {exc}") from exc
    finally:
        doc_path.unlink(missing_ok=True)


@app.post("/compare-html")
async def compare_doc_vs_html(
    document:  UploadFile = File(...),
    html_file: UploadFile = File(None),   # optional uploaded HTML
    html_path: str        = Form(""),     # optional local file path
) -> dict[str, Any]:
    """Compare a document against a downloaded HTML file (upload or local path)."""
    doc_path = _save_upload(document)
    try:
        # Resolve HTML source
        if html_file and html_file.filename:
            raw_html = (await html_file.read()).decode("utf-8", errors="replace")
            source   = html_file.filename
        elif html_path.strip():
            local = Path(html_path.strip())
            if not local.exists():
                raise HTTPException(400, f"File not found: {html_path}")
            raw_html = local.read_text(encoding="utf-8", errors="replace")
            source   = str(local)
        else:
            raise HTTPException(400, "Provide either an HTML file upload or a local file path.")

        parse_file  = _get_parser()
        doc_parsed  = parse_file(doc_path)
        html_parsed = _parse_html(raw_html, source)

        engine = _get_engine()
        report = engine.compare(doc_parsed, html_parsed)

        report_id   = uuid.uuid4().hex
        report_dict = _report_to_dict(report)
        report_dict["report_id"]       = report_id
        report_dict["compare_mode"]    = "doc_vs_html"
        report_dict["original_parsed"] = doc_parsed
        report_dict["new_parsed"]      = html_parsed
        _report_path(report_id).write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report_dict
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Comparison failed: {exc}") from exc
    finally:
        doc_path.unlink(missing_ok=True)


@app.post("/compare-web")
async def compare_doc_vs_web(
    document: UploadFile = File(...),
    url: str = Form(...),
) -> dict[str, Any]:
    """Upload a document and provide a URL; compare document content against the webpage."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "url must start with http:// or https://")

    doc_path = _save_upload(document)
    try:
        parse_file = _get_parser()
        doc_parsed = parse_file(doc_path)

        try:
            web_parsed = _scrape(url)
        except Exception as exc:
            raise HTTPException(502, f"Failed to fetch webpage: {exc}") from exc

        engine = _get_engine()
        report = engine.compare(doc_parsed, web_parsed)

        report_id = uuid.uuid4().hex
        report_dict = _report_to_dict(report)
        report_dict["report_id"] = report_id
        report_dict["compare_mode"] = "doc_vs_web"
        report_dict["original_parsed"] = doc_parsed
        report_dict["new_parsed"] = web_parsed
        _report_path(report_id).write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return report_dict
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Comparison failed: {exc}") from exc
    finally:
        doc_path.unlink(missing_ok=True)


# ── serialisation helper ──────────────────────────────────────────────────────

def _report_to_dict(report: Any) -> dict[str, Any]:
    d = asdict(report)
    # diff_lines lists are lists of str — fine for JSON
    return d
