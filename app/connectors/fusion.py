from pathlib import Path
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_file
from app.models import Document, User


def exported_files(directory: Path) -> list[Path]:
    """Discover user-provided Fusion exports; never attempts undocumented admin APIs or bypasses login."""
    allowed = {".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt", ".html", ".md"}
    if not directory.exists():
        return []
    return [p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in allowed]


def read_export(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".txt", ".csv", ".html", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".pdf":
        import fitz
        with fitz.open(path) as document:
            return "\n".join(page.get_text() for page in document)
    if path.suffix.lower() == ".docx":
        from docx import Document as DocxDocument
        return "\n".join(p.text for p in DocxDocument(path).paragraphs)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        from app.ingestion.structured import rows_from_file
        return "\n".join(str(row) for row in rows_from_file(path))
    raise ValueError("Unsupported Fusion export format")


def sync_fusion_directory(
    session: Session,
    directory: Path,
    owner: User | None = None,
    visibility: str = "roles",
    allowed_roles: list[str] | None = None,
) -> list[Document]:
    """
    Ingest all authorized Fusion export files found in the specified directory.
    Reuses the core ingestion pipeline to preserve versioning and deduplication.
    """
    files = exported_files(directory)
    ingested = []
    for file_path in files:
        doc = ingest_file(
            session=session,
            path=file_path,
            title=f"Fusion: {file_path.name}",
            source="fusion",
            owner=owner,
            visibility=visibility,
            allowed_roles=allowed_roles or ["faculty", "management", "admin"],
            external_id=f"fusion:{file_path.name}",
        )
        ingested.append(doc)
    return ingested
