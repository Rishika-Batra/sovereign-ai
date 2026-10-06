from app.db.database import SessionLocal
from app.db.models import DocumentChunk, Document
db = SessionLocal()
docs = db.query(Document).all()
for d in docs:
    print(f"Doc: {d.filename} (ID: {d.id})")
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).all()
    for c in chunks:
        print(f"  Chunk: {c.text[:100]}...")
