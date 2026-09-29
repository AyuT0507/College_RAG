import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, StructuredRecord, User
from app.security.access_control import visible_documents_query


def search_documents(session: Session, user: User, query: str, limit: int = 8) -> list[Document]:
    terms = [t for t in query.split() if len(t) > 2][:8]
    stmt = visible_documents_query(user)
    if terms:
        from sqlalchemy import or_
        stmt = stmt.where(or_(*(Document.title.ilike(f"%{term}%") for term in terms)))
    return list(session.scalars(stmt.order_by(Document.updated_at.desc()).limit(limit)).all())


def search_structured_records(session: Session, user: User, query: str, limit: int = 12) -> list[dict]:
    """Keyword search over ingested CSV/Excel rows, filtered by document visibility."""
    terms = [term.lower() for term in query.split() if len(term) > 2][:8]
    stmt = select(StructuredRecord, Document).join(Document, StructuredRecord.document_id == Document.id)
    visible = visible_documents_query(user).with_only_columns(Document.id).subquery()
    stmt = stmt.where(Document.id.in_(select(visible.c.id)))
    rows = session.execute(stmt.order_by(StructuredRecord.id.desc()).limit(1000)).all()
    matches = []
    for row, document in rows:
        values = json.loads(row.data_json)
        text = " ".join(f"{key}: {value}" for key, value in values.items())
        if not terms or any(term in text.lower() for term in terms):
            matches.append({"document_id": document.id, "text": f"{document.title} (row {row.row_number}): {text}"})
            if len(matches) >= limit:
                break
    return matches
