# SOP Ingestion Validation Tool

A local web application that parses Standard Operating Procedure (SOP) documents and compares them field-by-field and section-by-section against other documents, webpages, screenshots, downloaded HTML files, or in bulk via a CSV-driven batch mode.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Comparison Modes](#comparison-modes)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation and Startup](#installation-and-startup)
- [Using the Application](#using-the-application)
- [How Parsing Works](#how-parsing-works)
- [How Comparison Works](#how-comparison-works)

---

## Overview

When an SOP document is converted into a web page or another format, this tool validates that the content has been faithfully reproduced. It parses both sources into a common JSON schema, then compares them at the field level (title, version, author, etc.) and section level (each section's content), producing a scored report with MATCH / MISMATCH / MISSING / ADDED statuses.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Browser (Web UI)                       │
│         HTML + CSS + Vanilla JS (web/)                    │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP (multipart/form-data)
┌────────────────────────▼─────────────────────────────────┐
│              FastAPI Application (api/main.py)                    │
│  /compare  /compare-web  /compare-html  /compare-screenshot      │
│  /batch-compare-html                                              │
└──────┬─────────────────┬────────────────┬────────────────┘
       │                 │                │
┌──────▼──────┐  ┌───────▼──────┐  ┌─────▼──────────────┐
│   Parser    │  │  Web Scraper │  │    Image OCR        │
│ (parser/)   │  │(comparator/  │  │ (comparator/        │
│ PDF / DOCX  │  │web_scraper.py│  │  image_ocr.py)      │
└──────┬──────┘  └───────┬──────┘  └─────┬───────────────┘
       └─────────────────┴───────────────┘
                         │ Common SOP JSON schema
              ┌──────────▼──────────┐
              │    Diff Engine      │
              │(comparator/         │
              │ diff_engine.py)     │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Comparison Report  │
              │  (saved to reports/)|
              └─────────────────────┘
```

---

## Comparison Modes

| Mode | Description |
|---|---|
| **Doc vs Doc** | Compare two DOCX/PDF files directly |
| **Doc vs Webpage** | Upload a DOCX/PDF and provide a URL; the page is scraped and compared |
| **Doc vs Screenshot** | Upload a DOCX/PDF and a screenshot image; OCR extracts text from the image |
| **Doc vs HTML File** | Upload a DOCX/PDF and either upload a downloaded `.html` file or paste a local file path |
| **Batch Doc vs HTML** | Upload a CSV file to compare multiple DOCX/HTML pairs in one run; results saved to `batch_output\` |

---

## Project Structure

```
SOP_Ingestion_validation_tool/
├── api/
│   └── main.py              # FastAPI routes — /compare, /compare-web, /compare-html, /compare-screenshot, /batch-compare-html
├── comparator/
│   ├── diff_engine.py       # Field + section comparison, similarity scoring, diff generation
│   ├── web_scraper.py       # Fetches a URL or parses HTML; extracts sections from CREW Blazor pages
│   ├── image_ocr.py         # Tesseract OCR wrapper; converts an image to the SOP JSON schema
│   └── report_html.py       # Generates self-contained HTML comparison reports for batch output
├── parser/
│   ├── base_parser.py       # Abstract base: shared regex patterns, parse() method
│   ├── docx_parser.py       # python-docx parser; reads paragraphs and tables in document order
│   └── pdf_parser.py        # pdfplumber parser
├── schemas/
│   └── sop_schema.json      # JSON schema for the common SOP document structure
├── web/
│   ├── index.html           # Single-page UI
│   ├── app.js               # Client-side logic for all five comparison modes
│   ├── styles.css           # Styling
│   └── williams_logo.png    # Williams logo displayed in the application header
├── uploads/                 # Temporary upload storage (auto-deleted after each request)
├── reports/                 # Persisted single-comparison reports (JSON, one file per run)
├── batch_output/            # Batch comparison output — one .json and one .html per DOCX file
├── requirements.txt
└── start.bat                # One-click launcher for Windows
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | [python.org](https://www.python.org/downloads/) |
| **pip** | Bundled with Python |
| **Tesseract OCR** *(optional)* | Required only for Doc vs Screenshot mode |

### Installing Tesseract OCR (Windows)

1. Download the installer from [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Run the installer — the default installation path is:
   `C:\Users\<your-username>\AppData\Local\Programs\Tesseract-OCR\`
3. No manual PATH configuration is required — the tool auto-detects common install locations.

---

## Installation and Startup

### Option A — One-click (Windows)

Double-click **`start.bat`** in the project root.

It will:
1. Install all Python dependencies from `requirements.txt`
2. Check whether Tesseract is installed and warn if not
3. Start the server at `http://localhost:8000`

### Option B — Manual

```powershell
# From the project root folder
cd C:\Winnie\SOP_Ingestion_validation_tool

# Install dependencies
pip install -r requirements.txt

# Set Python path and start the server
$env:PYTHONPATH = (Get-Location).Path
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# If you get block on windows. run below command instead
#python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser once the server is running.

---

## Using the Application

1. Select a comparison mode from the top navigation bar.
2. Upload the required files (and/or paste a URL or local file path).
3. Click the **Compare** button.
4. Review the results:
   - **Summary banner** — overall match score and status counts
   - **Field Comparison tab** — row-by-row comparison of metadata fields (title, version, author, etc.)
   - **Section Comparison tab** — side-by-side section content with inline word-level diff highlights
   - **Raw JSON tab** — full parsed JSON for both documents

### Batch Doc vs HTML

1. Select the **Batch Doc vs HTML** tab.
2. Prepare a CSV file — no header row, two columns per row:

   ```
   C:\Docs\Procedure1.docx,C:\HTML\Procedure1.html
   C:\Docs\SafetyGuide.docx,C:\HTML\SafetyGuide.html
   ```

3. Upload the CSV and click **Run Batch Compare**.
4. The tool processes every row and displays a results table showing the status, match score, and output file paths for each pair.
5. Output files are saved to `batch_output\` in the project root:
   - `<docx-stem>.json` — full comparison report
   - `<docx-stem>.html` — self-contained, styled HTML report with inline diff highlights that can be opened directly in a browser

### Supported File Types

| Format | Parsing Method |
|---|---|
| `.docx` | python-docx — paragraphs and tables read in document order |
| `.pdf` | pdfplumber — text extracted page by page |
| `.html` / `.htm` | BeautifulSoup4 — scoped to `div.crew-rendered-content` when present |
| `.png`, `.jpg`, `.webp`, `.bmp`, `.tiff` | Tesseract OCR via pytesseract |

> **Note:** Legacy `.doc` (Word 97 binary) files are not supported. Open the file in Word and save as **Word Document (.docx)** before uploading.

---

## How Parsing Works

All parsers produce a common JSON document with these top-level fields:

```
document_id, title, version, revision_date, effective_date,
department, author, approver, purpose, scope,
sections[], warnings[], references[], revisions[], metadata{}
```

**DOCX parser** walks the document body XML element-by-element (paragraphs and tables in order). Headings (`Heading 1–4` styles or fully-bold lines) mark section boundaries. Tables found within a section are appended to that section's content. The first table in the document (typically a cover/header table) is skipped from section content.

**HTML / web scraper** scopes all parsing to `div.crew-rendered-content` when present. If a `div.crew-document` container is found inside, it walks its direct children treating `div.crew-section` elements as headings (CREW Blazor structure). Otherwise it falls back to standard `h1–h6` heading detection. The document title is extracted from `div.crew-header-title` if present.

---

## How Comparison Works

The **Diff Engine** (`comparator/diff_engine.py`) runs in three passes:

1. **Scalar field comparison** — each metadata field is compared with `difflib.SequenceMatcher`. Fields with similarity ≥ 0.80 are MATCH; below that threshold they are MISMATCH.

2. **Section matching** — sections are matched in two passes:
   - **Pass 1 (title match):** Normalised titles are compared after stripping leading numeric prefixes (`1.`, `2.3.`, etc.) and non-alphanumeric characters. Example: `"Execute PSSR"` matches `"1. Execute PSSR"`.
   - **Pass 2 (content fallback):** Sections with no title match are paired by content similarity (threshold 0.40). This handles cases where the DOCX uses a generic title like `"Table"` and the HTML uses a meaningful title like `"Forms"` for the same content.
   - **Pass 3:** Any remaining unmatched sections are reported as MISSING (present in original only) or ADDED (present in new version only).

3. **Scoring** — the overall match score is `MATCH count ÷ total items`. Single-mode reports are persisted as JSON under `reports/`; batch reports are saved to `batch_output/`.

**Batch processing** (`POST /batch-compare-html`) reads a CSV row by row. Each row is processed independently — a failure on one row (missing file, parse error) is recorded in the results table without stopping the remaining rows. Output filenames are derived from the DOCX file stem, so `MyProcedure.docx` produces `batch_output\MyProcedure.json` and `batch_output\MyProcedure.html`.
