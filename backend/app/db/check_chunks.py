from app.db.database import SessionLocal
from app.db.models import DocumentChunk

def check_chunks():
    db = SessionLocal()
    try:
        chunks = db.query(DocumentChunk).all()
        print(f"Total DocumentChunks in DB: {len(chunks)}\n")
        for chunk in chunks:
            text_snippet = chunk.text.replace("\n", " ")[:80] if chunk.text else ""
            print(f"Doc ID: {chunk.document_id} | Page: {chunk.page} | Text: {text_snippet}...")
    finally:
        db.close()

if __name__ == "__main__":
    check_chunks()
