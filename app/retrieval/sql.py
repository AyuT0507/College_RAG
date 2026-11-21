import json
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Document, StructuredRecord, User
from app.security.access_control import visible_documents_query


def search_documents(session: Session, user: User, query: str, limit: int = 8) -> list[Document]:
    """Search document metadata (e.g. titles) using SQL ILIKE queries."""
    terms = [t.strip() for t in query.split() if len(t.strip()) > 2][:8]
    stmt = visible_documents_query(user)
    if terms:
        stmt = stmt.where(or_(*(Document.title.ilike(f"%{term}%") for term in terms)))
    return list(session.scalars(stmt.order_by(Document.updated_at.desc()).limit(limit)).all())


def search_structured_records(session: Session, user: User, query: str, limit: int = 15) -> list[dict]:
    """
    Search structured CSV/Excel records using SQL filtering.
    Performs database-level ILIKE / contains searches and aggregation (e.g., counting).
    """
    # Extract meaningful search tokens (ignoring common query noise)
    stop_words = {"how", "many", "what", "which", "are", "the", "for", "and", "count", "list", "all", "show"}
    terms = [t.lower().strip() for t in re.findall(r"\w+", query) if len(t) > 2 and t.lower() not in stop_words][:8]
    
    visible_subq = visible_documents_query(user).with_only_columns(Document.id).subquery()
    
    # Base SQL query joining StructuredRecord with visible Documents
    base_stmt = (
        select(StructuredRecord, Document)
        .join(Document, StructuredRecord.document_id == Document.id)
        .where(Document.id.in_(select(visible_subq.c.id)))
    )

    # Push search filter directly down to SQL engine
    if terms:
        conditions = [StructuredRecord.data_json.ilike(f"%{term}%") for term in terms]
        filter_stmt = base_stmt.where(or_(*conditions))
    else:
        filter_stmt = base_stmt

    # If the user asks for count/total, run a SQL COUNT aggregation
    is_count_query = bool(re.search(r"\b(how many|count|total number of)\b", query.lower()))
    matches: list[dict] = []

    if is_count_query:
        count_stmt = (
            select(func.count(StructuredRecord.id))
            .join(Document, StructuredRecord.document_id == Document.id)
            .where(Document.id.in_(select(visible_subq.c.id)))
        )
        if terms:
            count_stmt = count_stmt.where(or_(*(StructuredRecord.data_json.ilike(f"%{t}%") for t in terms)))
        total_count = session.scalar(count_stmt) or 0
        matches.append({
            "document_id": -1,
            "text": f"SQL Aggregation: Found a total of {total_count} structured records matching criteria ({', '.join(terms) if terms else 'all'})."
        })

    # Fetch matching rows via SQL
    rows = session.execute(filter_stmt.order_by(StructuredRecord.id.desc()).limit(limit)).all()

    for row, document in rows:
        try:
            values = json.loads(row.data_json)
            formatted = ", ".join(f"{k}: {v}" for k, v in values.items() if v not in (None, ""))
            matches.append({
                "document_id": document.id,
                "text": f"[{document.title} | Row {row.row_number}] {formatted}"
            })
        except Exception:
            matches.append({
                "document_id": document.id,
                "text": f"[{document.title} | Row {row.row_number}] {row.data_json}"
            })

    return matches
