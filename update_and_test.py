import asyncio
from app.db.database import SessionLocal
from app.db.models import Agent, User
from app.api.agents import run_agent
from app.api.schemas import AgentRunRequest

async def main():
    db = SessionLocal()
    agent = db.query(Agent).filter(Agent.name == "Inspection Analyst").first()
    if agent:
        agent.prompt_template = "Analyze the inspection findings for {target}. First, search the knowledge base for '{target}' and use read_file to read the full document. Based ONLY on the specific component statuses and numeric readings found in that file, provide your analysis directly as text in your final response (do not generate a document file): (1) a specific summary of each component's condition and reading, (2) an overall risk level (Low/Medium/High/Critical) with justification citing the specific readings, and (3) a recommended next action."
        db.commit()

    admin = db.query(User).filter(User.role == "admin").first()
    req = AgentRunRequest(variables={"target": "M-104"})
    res = await run_agent(agent_id=agent.id, request=req, db=db, current_user=admin)
    print("FINAL ANSWER:", res["final_answer"])
    print("STEPS:", [s["tool"] for s in res["steps"]])

asyncio.run(main())
