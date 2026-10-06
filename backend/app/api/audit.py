from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import AuditLog, User
from app.api.deps import get_db, require_permission
from app.api.schemas import AuditLogResponse

router = APIRouter()


@router.get("/logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit.view")),
):
    """
    Returns the most recent 100 audit log entries.
    Requires 'audit.view' permission.
    """
    entries = (
        db.query(AuditLog)
        .order_by(desc(AuditLog.created_at))
        .limit(100)
        .all()
    )
    result = []
    for entry in entries:
        result.append(
            AuditLogResponse(
                id=entry.id,
                user_id=entry.user_id,
                user_email=entry.user.email if entry.user else None,
                action=entry.action,
                resource=entry.resource,
                details=entry.details,
                created_at=entry.created_at,
            )
        )
    return result
