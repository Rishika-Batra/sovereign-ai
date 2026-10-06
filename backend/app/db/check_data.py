from app.db.database import SessionLocal
from app.db.models import Message

def check_data():
    db = SessionLocal()
    try:
        messages = db.query(Message).all()
        print(f"Total messages in DB: {len(messages)}")
        for msg in messages:
            print(f"[{msg.created_at}] Session {msg.session_id} | {msg.role}: {msg.content}")
    finally:
        db.close()

if __name__ == "__main__":
    check_data()
