import inspect
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import User, ChatSession, Message
from app.api.deps import get_db, get_current_user, require_permission
from app.services.audit import log_action
from app.agent.tools import TOOLS
from app.agent.graph import agent_graph

router = APIRouter()


class TestToolRequest(BaseModel):
    tool_name: str
    args: Dict[str, Any] = {}


class RunAgentRequest(BaseModel):
    task: str
    session_id: int | None = None


@router.post("/test-tool")
async def test_tool_endpoint(
    request: TestToolRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Test endpoint (admin-only) to execute individual agent tools in isolation.
    generate_* tools are still gated by the risk check even here.
    All invocations are audit-logged.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Risk gate — prevent admins from bypassing approval via test-tool
    from app.agent.risk import is_action_risky
    if is_action_risky(tool_name=request.tool_name):
        log_action(
            db=db,
            user=current_user,
            action="test_tool_blocked",
            resource="agent",
            details={"tool": request.tool_name, "reason": "risk gate"},
        )
        raise HTTPException(
            status_code=403,
            detail=f"Tool '{request.tool_name}' is a high-risk action and cannot be executed via test-tool.",
        )

    tool_func = TOOLS.get(request.tool_name)
    if not tool_func:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{request.tool_name}' not found. Available tools: {list(TOOLS.keys())}",
        )

    tool_args = request.args.copy() if request.args else {}

    # Dynamically inject db and/or user parameters if required by tool signature
    sig = inspect.signature(tool_func)
    if "db" in sig.parameters:
        tool_args["db"] = db
    if "user" in sig.parameters:
        tool_args["user"] = current_user

    log_action(
        db=db,
        user=current_user,
        action="test_tool",
        resource="agent",
        details={"tool": request.tool_name, "args": request.args},
    )

    try:
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**tool_args)
        else:
            result = tool_func(**tool_args)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing tool '{request.tool_name}': {str(e)}",
        )

    return {
        "tool_name": request.tool_name,
        "result": result,
    }


@router.post("/run")
async def run_agent_endpoint(
    request: RunAgentRequest,
    current_user: User = Depends(require_permission("agent.run")),
    db: Session = Depends(get_db),
):
    """
    Executes the LangGraph agent reasoning loop for a given task.
    Returns final_answer and the step-by-step tool execution history.
    """
    # Handle Session Creation
    session = None
    if request.session_id:
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    
    if not session:
        title = request.task[:50] + "..." if len(request.task) > 50 else request.task
        session = ChatSession(user_id=current_user.id, title=title)
        db.add(session)
        db.commit()
        db.refresh(session)
        
    # Save user message
    user_message = Message(session_id=session.id, role="user", content=request.task)
    db.add(user_message)
    db.commit()

    initial_state = {
        "task": request.task,
        "user": current_user,
        "db": db,
        "history": [],
        "pending_tool": None,
        "final_answer": None,
        "step_count": 0,
        "session_id": session.id,
        "awaiting_approval": False,
        "pending_action_id": None,
    }

    final_state = await agent_graph.ainvoke(initial_state)

    steps = final_state.get("history", [])
    tools_called = [step.get("tool") for step in steps if isinstance(step, dict) and step.get("tool")]

    log_action(
        db=db,
        user=current_user,
        action="agent_run",
        resource="agent",
        details={
            "task": request.task,
            "tools_called": tools_called,
        },
    )

    final_answer = final_state.get("final_answer")
    awaiting_approval = final_state.get("awaiting_approval", False)

    # Save assistant message if there's a final answer and not awaiting approval
    if final_answer and not awaiting_approval:
        assistant_message = Message(session_id=session.id, role="assistant", content=final_answer)
        db.add(assistant_message)
        db.commit()

    return {
        "session_id": session.id,
        "final_answer": final_answer,
        "steps": steps,
        "awaiting_approval": awaiting_approval,
        "pending_action_id": final_state.get("pending_action_id"),
    }
