import sys
import os
import hashlib

sys.path.append("/app")

from app.db.database import SessionLocal
from app.db.models import DocumentStatus

def main():
    db = SessionLocal()
    docs = db.query(DocumentStatus).filter(DocumentStatus.file_hash.is_(None)).all()
    print(f"Found {len(docs)} documents without a file_hash.")
    
    upload_dir = "/app/uploads"
    updated = 0
    
    for doc in docs:
        file_path = None
        for entry in os.listdir(upload_dir):
            if entry.startswith(doc.document_id):
                file_path = os.path.join(upload_dir, entry)
                break
                
        if file_path and os.path.isfile(file_path):
            try:
                h = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        h.update(chunk)
                doc.file_hash = h.hexdigest()
                updated += 1
            except Exception as e:
                print(f"Failed to hash {file_path}: {e}")
                
    db.commit()
    db.close()
    print(f"Successfully backfilled {updated} file hashes.")

if __name__ == "__main__":
    main()
