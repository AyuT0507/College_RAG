from pathlib import Path

import fitz
import json
from docx import Document as DocxDocument


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        with fitz.open(path) as pdf:
            return "\n".join(page.get_text() for page in pdf)
    if suffix == ".docx":
        doc = DocxDocument(path)
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix in {".xlsx", ".xls"}:
        from app.ingestion.structured import rows_from_file
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows_from_file(path))
    if suffix in {".txt", ".md", ".csv"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Supported uploads: PDF, DOCX, TXT, MD, CSV")


def chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        result.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return result
