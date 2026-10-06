from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import User, Deliverable
from app.api.deps import get_db
from app.api.deps import get_current_user, require_permission
from pydantic import BaseModel, field_serializer
from datetime import datetime

router = APIRouter()

class DeliverableResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    generated_by: int | None
    created_at: datetime
    download_path: str

    class Config:
        from_attributes = True

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        """Return UTC ISO 8601 string with 'Z' suffix so the browser
        treats it as UTC, not as the server's local time."""
        if value is None:
            return None
        # value is a naive UTC datetime (stored via datetime.utcnow)
        return value.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


@router.get("/", response_model=List[DeliverableResponse])
def get_deliverables(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """List all generated deliverables."""
    return db.query(Deliverable).order_by(desc(Deliverable.created_at)).all()

