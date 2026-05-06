from pathlib import Path
from typing import Any

from .pdf_parser import PdfParser
from .docx_parser import DocxParser


def parse_file(file_path: str | Path) -> dict[str, Any]:
    """Parse a PDF or DOCX file and return a schema-conformant dict."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return PdfParser(path).parse()
    if ext in {".docx", ".doc"}:
        return DocxParser(path).parse()
    raise ValueError(f"Unsupported file type: {ext}")
