import asyncio
from app.db.database import SessionLocal
from app.api.agents import run_agent
from app.api.schemas import AgentRunRequest
from app.db.models import User

async def main():
    db = SessionLocal()
    admin = db.query(User).filter(User.role == "admin").first()
    req = AgentRunRequest(variables={"target": "M-104"})
    res = await run_agent(agent_id=1, request=req, db=db, current_user=admin)
    print("FINAL ANSWER:", res["final_answer"])
    print("STEPS:", [s["tool"] for s in res["steps"]])

asyncio.run(main())
