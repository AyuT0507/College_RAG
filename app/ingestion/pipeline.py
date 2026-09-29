import hashlib
import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingestion.documents import chunks, extract_text
from app.models import Document, DocumentVersion, StructuredRecord, User
from app.retrieval.vector import upsert_document
from app.ingestion.structured import rows_from_file


def ingest_file(session: Session, path: Path, *, title: str, source: str, owner: User | None,
                visibility: str = "private", allowed_roles: list[str] | None = None,
                external_id: str = "") -> Document:
    text = extract_text(path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    owner_id = owner.id if owner else None
    doc = session.scalar(select(Document).where(Document.owner_id == owner_id, Document.source == source,
                                                Document.external_id == external_id)) if external_id else None
    if doc and doc.content_hash == digest:
        return doc
    if not doc:
        doc = Document(title=title, source=source, external_id=external_id, owner_id=owner_id,
                       visibility=visibility, allowed_roles=",".join(allowed_roles or []), content_hash=digest)
        session.add(doc)
        session.flush()
    else:
        doc.current_version += 1
        doc.content_hash = digest
        doc.title = title
        doc.visibility, doc.allowed_roles = visibility, ",".join(allowed_roles or [])
    version = doc.current_version
    dest = path.parent / "versions" / str(doc.id) / f"{version}_{path.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.resolve() != dest.resolve():
        dest.write_bytes(path.read_bytes())
    session.add(DocumentVersion(document=doc, version=version, content_hash=digest, storage_path=str(dest)))
    session.flush()
    if path.suffix.lower() in {".csv", ".xlsx", ".xls"}:
        session.execute(delete(StructuredRecord).where(StructuredRecord.document_id == doc.id))
        for index, row in enumerate(rows_from_file(path), start=1):
            session.add(StructuredRecord(document_id=doc.id, row_number=index,
                                         data_json=json.dumps(row, ensure_ascii=False, default=str)))
    upsert_document(doc.id, owner_id, visibility, doc.allowed_roles, chunks(text))
    return doc
