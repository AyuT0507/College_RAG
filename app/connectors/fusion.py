from pathlib import Path


def exported_files(directory: Path) -> list[Path]:
    """Discover user-provided Fusion exports; never attempts undocumented admin APIs or bypasses login."""
    allowed = {".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt", ".html"}
    return [p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in allowed]


def read_export(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".txt", ".csv", ".html"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".pdf":
        import fitz
        with fitz.open(path) as document:
            return "\n".join(page.get_text() for page in document)
    if path.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        from app.ingestion.structured import rows_from_file
        return "\n".join(str(row) for row in rows_from_file(path))
    raise ValueError("Unsupported Fusion export format")
