from typing import Any, Optional

PERMISSIONS = {
    "employee": {"chat", "documents.read", "documents.upload", "agent.run"},
    "engineer": {"chat", "documents.read", "documents.upload", "agent.run", "documents.manage"},
    "manager": {"chat", "documents.read", "documents.upload", "agent.run", "audit.view", "documents.manage", "actions.approve"},
    "admin": {
        "chat",
        "documents.read",
        "documents.upload",
        "agent.run",
        "users.manage",
        "audit.view",
        "documents.manage",
        "settings.manage",
        "actions.approve",
    },
}

def has_permission(user: Any, permission: str) -> bool:
    """
    Checks if a given user has the specified permission based on their role.
    Legacy role 'user' is mapped to 'employee'.
    """
    if not user or not hasattr(user, "role") or not user.role:
        return False

    role = user.role
    if role == "user":
        role = "employee"

    user_perms = PERMISSIONS.get(role, set())
    return permission in user_perms
