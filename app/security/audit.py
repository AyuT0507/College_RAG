import json
from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(session: Session, action: str, user_id: int | None = None,
                 details: dict | str = "", ip_address: str = "") -> AuditLog:
    """Record an audit trail entry for compliance and security monitoring."""
    if isinstance(details, dict):
        details_str = json.dumps(details, ensure_ascii=False)
    else:
        details_str = str(details)
    entry = AuditLog(
        user_id=user_id,
        action=action,
        details=details_str,
        ip_address=ip_address,
    )
    session.add(entry)
    session.flush()
    return entry
