from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentVersion


def versions_for(session: Session, document_id: int) -> list[DocumentVersion]:
    return list(session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                               .order_by(DocumentVersion.version.desc())).all())
