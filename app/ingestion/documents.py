import json
from pathlib import Path


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
            with fitz.open(path) as pdf:
                return "\n".join(page.get_text() for page in pdf)
        except ImportError:
            raise ValueError("PyMuPDF (fitz) is required to process PDF files. Run 'pip install pymupdf'.")
    if suffix == ".docx":
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            raise ValueError("python-docx is required to process DOCX files. Run 'pip install python-docx'.")
    if suffix in {".xlsx", ".xls"}:
        from app.ingestion.structured import rows_from_file
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows_from_file(path))
    if suffix in {".txt", ".md", ".csv", ".html"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported file format: {suffix}. Supported: PDF, DOCX, TXT, MD, CSV, XLSX, XLS")


def chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Split text into overlapping token-sized character chunks for vector embedding."""
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
