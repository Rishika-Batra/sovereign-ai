# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from typing import List, Annotated
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
import re

from app.db.models import User
from app.api.deps import get_db, require_permission
from app.core.security import get_password_hash
from app.services.audit import log_action

router = APIRouter()

ALLOWED_ROLES = {"employee", "engineer", "manager", "admin"}

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    workspace: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    email: str
    password: str
    role: str
    workspace: str

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Accept any user@domain.tld including .local / internal domains."""
        pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
        if not re.match(pattern, v.strip()):
            raise ValueError(f"'{v}' is not a valid email address format.")
        return v.strip().lower()

class UserRoleUpdate(BaseModel):
    role: str

@router.get("/", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    users = db.query(User).all()
    return users

@router.post("/", response_model=UserResponse)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    if user_in.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Allowed roles are: {', '.join(ALLOWED_ROLES)}"
        )
    
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    new_user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role,
        workspace=user_in.workspace,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_action(db, current_user, action="user_created", resource="users", details={"user_id": new_user.id, "email": new_user.email, "role": new_user.role})

    return new_user

@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    if role_update.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Allowed roles are: {', '.join(ALLOWED_ROLES)}"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    old_role = user.role
    user.role = role_update.role
    db.commit()
    db.refresh(user)

    log_action(db, current_user, action="user_role_changed", resource="users", details={"user_id": user.id, "email": user.email, "old_role": old_role, "new_role": user.role})

    return user
