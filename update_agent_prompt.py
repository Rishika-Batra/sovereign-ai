from app.db.database import SessionLocal
from app.db.models import Agent

db = SessionLocal()
agent = db.query(Agent).filter(Agent.name == "Inspection Analyst").first()
if agent:
    agent.prompt_template = "Analyze the inspection findings for {target}. Based on the component statuses and readings found, provide: (1) a summary of each component's condition, (2) an overall risk level (Low/Medium/High/Critical) with justification, and (3) a recommended next action."
    db.commit()
    print("Agent prompt updated successfully.")
