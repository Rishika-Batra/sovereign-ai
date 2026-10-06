from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from datetime import datetime
import inspect

from app.db.database import engine
from app.db.models import User, PendingAction, Message
from app.api.deps import get_db, get_current_user, require_permission
from app.services.audit import log_action
from app.agent.tools import TOOLS

router = APIRouter()

class PendingActionResponse(BaseModel):
    id: int
    user_id: int
    session_id: Optional[int]
    tool: str
    arguments: Dict[str, Any]
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class RejectRequest(BaseModel):
    reason: Optional[str] = None

class ModifyRequest(BaseModel):
    arguments: Dict[str, Any]

@router.get("", response_model=List[PendingActionResponse])
def get_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get pending actions.
    If user has actions.approve, they see pending actions for their workspace.
    Otherwise, they only see their own pending actions.
    """
    from app.core.permissions import has_permission
    
    query = db.query(PendingAction).filter(PendingAction.status == "pending")
    
    if has_permission(current_user, "actions.approve"):
        # Can see workspace approvals, but admins see all or their workspace?
        # Requirement: "managers/admins see their workspace's"
        if current_user.role != "admin":
            query = query.join(User).filter(User.workspace == current_user.workspace)
    else:
        query = query.filter(PendingAction.user_id == current_user.id)
        
    return query.order_by(PendingAction.created_at.desc()).all()


async def execute_pending_action(
    action: PendingAction,
    arguments: dict,
    db: Session,
    executing_user: User,       # the approver — used for audit context
    requester_user: User,       # the original requester — attributed as generated_by
):
    """Executes the tool or final answer and saves result to chat session."""
    tool_name = action.tool
    
    if tool_name == "final_answer":
        result = arguments.get("final_answer", "")
    else:
        tool_func = TOOLS.get(tool_name)
        if not tool_func:
            raise HTTPException(status_code=500, detail=f"Tool {tool_name} not found")
            
        call_args = arguments.copy()
        sig = inspect.signature(tool_func)
        if "db" in sig.parameters:
            call_args["db"] = db
        if "user" in sig.parameters:
            # Pass the original requester so generated_by is correct
            call_args["user"] = requester_user
            
        try:
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**call_args)
            else:
                result = tool_func(**call_args)
        except Exception as e:
            result = f"Error executing {tool_name}: {str(e)}"
            
        # Format the result nicely if it's a generated file
        TERMINAL_TOOLS = {"generate_docx", "generate_xlsx", "generate_pdf", "generate_pptx"}
        if tool_name in TERMINAL_TOOLS and isinstance(result, str) and "Download at:" in result:
            import re
            url_match = re.search(r"(/api/documents/download/\S+)", result)
            download_url = url_match.group(1) if url_match else result
            result = f"I've generated the document. You can download it here: {download_url}"
            
    # Save the assistant message to the chat session
    if action.session_id:
        assistant_message = Message(session_id=action.session_id, role="assistant", content=str(result))
        db.add(assistant_message)
        db.commit()


@router.post("/{action_id}/approve")
async def approve_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("actions.approve")),
):
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")
        
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Action already {action.status}")
        
    if action.user_id == current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You cannot approve your own action unless you are an admin")
        
    action.status = "approved"
    db.commit()
    
    log_action(db, current_user, "action_approved", "approvals", {"action_id": action.id, "tool": action.tool})
    
    # Fetch the original requester so generated_by is attributed to them
    requester = db.query(User).filter(User.id == action.user_id).first() or current_user
    await execute_pending_action(action, action.arguments, db, current_user, requester)
    return {"status": "success", "message": "Action approved and executed"}


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("actions.approve")),
):
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")
        
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Action already {action.status}")
        
    if action.user_id == current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You cannot reject your own action unless you are an admin")
        
    action.status = "rejected"
    db.commit()
    
    reason = payload.reason or "No reason provided"
    log_action(db, current_user, "action_rejected", "approvals", {"action_id": action.id, "tool": action.tool, "reason": reason})
    
    # Save rejection to chat session
    if action.session_id:
        msg = f"Action '{action.tool}' was rejected by an approver. Reason: {reason}"
        assistant_message = Message(session_id=action.session_id, role="assistant", content=msg)
        db.add(assistant_message)
        db.commit()
        
    return {"status": "success", "message": "Action rejected"}


@router.post("/{action_id}/modify")
async def modify_action(
    action_id: int,
    payload: ModifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("actions.approve")),
):
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")
        
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Action already {action.status}")
        
    if action.user_id == current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You cannot modify and approve your own action unless you are an admin")
        
    action.status = "modified"
    action.arguments = payload.arguments
    db.commit()
    
    log_action(db, current_user, "action_modified", "approvals", {"action_id": action.id, "tool": action.tool})
    
    # Fetch the original requester so generated_by is attributed to them
    requester = db.query(User).filter(User.id == action.user_id).first() or current_user
    await execute_pending_action(action, payload.arguments, db, current_user, requester)
    return {"status": "success", "message": "Action modified and executed"}
