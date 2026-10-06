import asyncio
from app.db.database import SessionLocal
from app.db.models import Agent, User
from app.api.agents import run_agent
from app.api.schemas import AgentRunRequest

async def main():
    db = SessionLocal()
    agent = db.query(Agent).filter(Agent.name == "Inspection Analyst").first()
    if agent:
        agent.prompt_template = "Analyze the inspection findings for {target}. Based on the component statuses and readings found, provide: (1) a summary of each component's condition, (2) an overall risk level (Low/Medium/High/Critical) with justification, and (3) a recommended next action."
        db.commit()

    admin = db.query(User).filter(User.role == "admin").first()
    req = AgentRunRequest(variables={"target": "M-104"})
    res = await run_agent(agent_id=agent.id, request=req, db=db, current_user=admin)
    print("FINAL ANSWER:", res["final_answer"])
    print("STEPS:", [s["tool"] for s in res["steps"]])

asyncio.run(main())
