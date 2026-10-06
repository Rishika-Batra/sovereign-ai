from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models import User, AuditLog


def log_action(
    db: Session,
    user: Optional[User],
    action: str,
    resource: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Writes an audit entry to the AuditLog table.
    """
    user_id = user.id if user else None
    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        details=details or {},
        created_at=datetime.utcnow(),
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry
