from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models import User, Agent
from app.db.database import SessionLocal
from app.api.deps import get_current_user, require_permission, get_db
from app.api.schemas import AgentCreate, AgentResponse, AgentRunRequest
from app.agent.graph import agent_graph
from app.services.audit import log_action

router = APIRouter()

@router.get("/", response_model=List[AgentResponse])
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available agents."""
    return db.query(Agent).order_by(desc(Agent.created_at)).all()


@router.post("/", response_model=AgentResponse)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent.run")), # Only those who can run agents can create them
):
    """Create a new predefined agent (prompt template)."""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to create agents.")
        
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Agent name cannot be empty.")
        
    existing = db.query(Agent).filter(Agent.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="An agent with this name already exists.")

    agent = Agent(
        name=name,
        description=payload.description.strip(),
        prompt_template=payload.prompt_template.strip(),
        created_by=current_user.id
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    log_action(db, current_user, "create_agent", "agent", {"agent_id": agent.id, "name": agent.name})
    return agent


@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: int,
    request: AgentRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent.run")),
):
    """
    Executes a predefined agent by substituting variables into its prompt template
    and passing the result to the LangGraph agent reasoning loop.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # Substitute variables into the prompt template
    try:
        # We format safely, ignoring missing keys if the template doesn't strict require it, 
        # but str.format will raise KeyError if a placeholder is missing.
        formatted_task = agent.prompt_template.format(**request.variables)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing variable for placeholder: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid template format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error formatting template: {str(e)}")

    initial_state = {
        "task": formatted_task,
        "user": current_user,
        "db": db,
        "history": [],
        "pending_tool": None,
        "final_answer": None,
        "step_count": 0,
        "session_id": None,
        "awaiting_approval": False,
        "pending_action_id": None,
    }

    final_state = await agent_graph.ainvoke(initial_state)

    steps = final_state.get("history", [])
    tools_called = [step.get("tool") for step in steps if isinstance(step, dict) and step.get("tool")]

    log_action(
        db=db,
        user=current_user,
        action="predefined_agent_run",
        resource="agent",
        details={
            "agent_id": agent.id,
            "agent_name": agent.name,
            "variables": request.variables,
            "task": formatted_task,
            "tools_called": tools_called,
        },
    )

    final_answer = final_state.get("final_answer")
    awaiting_approval = final_state.get("awaiting_approval", False)
    
    if awaiting_approval:
        final_answer = None

    return {
        "final_answer": final_answer,
        "steps": steps,
        "formatted_task": formatted_task,
        "awaiting_approval": awaiting_approval,
        "pending_action_id": final_state.get("pending_action_id"),
    }
