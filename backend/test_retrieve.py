import sys
import asyncio
sys.path.append("/app")
from app.db.database import SessionLocal
from app.db.models import User
from app.services.retrieve import retrieve_context

async def main():
    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        print("No user")
        return
    res = await retrieve_context(db, "test", user)
    print("Found:", len(res))

if __name__ == "__main__":
    asyncio.run(main())
