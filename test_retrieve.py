import asyncio
from app.db.database import SessionLocal
from app.db.models import User
from app.services.retrieve import retrieve_context

async def main():
    db = SessionLocal()
    admin = db.query(User).filter(User.role == "admin").first()
    results = await retrieve_context(db=db, query="M-104", user=admin)
    for r in results:
        print(f"Doc: {r['filename']} - Text: {r['text'][:100]}")

asyncio.run(main())
