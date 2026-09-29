from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Document, User


def can_upload(user: User) -> bool:
    return user.is_active and user.role in {"faculty", "management", "admin"}


def visible_documents_query(user: User):
    role_match = Document.allowed_roles == ""
    # Comma-delimited exact role membership without granting substring matches.
    role_match = or_(role_match, Document.allowed_roles.like(f"%,{user.role},%"),
                     Document.allowed_roles.like(f"{user.role},%"),
                     Document.allowed_roles.like(f"%,{user.role}"), Document.allowed_roles == user.role)
    return select(Document).where(or_(Document.visibility == "public", Document.owner_id == user.id,
                                      (Document.visibility == "roles") & role_match))


def visible_document_ids(session: Session, user: User) -> set[int]:
    return set(session.scalars(visible_documents_query(user).with_only_columns(Document.id)).all())
