from app.db.database import SessionLocal
from app.db.models import Document, DocumentChunk
db = SessionLocal()
docs = db.query(Document).all()
for d in docs:
    print(d.id, d.filename)
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).all()
    for c in chunks:
        if "M-104" in c.text:
            print("  Contains M-104:", repr(c.text))
