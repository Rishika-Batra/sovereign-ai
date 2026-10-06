import os
import uuid
import shutil
import traceback
import hashlib
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, or_
from jose import jwt, JWTError

from app.db.models import User, DocumentChunk, DocumentStatus, Workspace, DocumentAcl
from app.db.database import SessionLocal
from app.api.deps import get_db, get_current_user, get_optional_user, require_permission
from app.api.schemas import DocumentInfoResponse, KnowledgeBaseSummary, WorkspaceResponse
from app.core.security import SECRET_KEY, ALGORITHM
from app.services.ingest import (
    extract_text_pymupdf, is_scanned, chunk_text,
    ocr_scanned_pdf, extract_text_docx, extract_text_xlsx, extract_text_xls,
    extract_text_image, serialize_document,
)
from app.ai_gateway.gateway import gateway
from app.services.audit import log_action

UPLOAD_DIR = "/app/uploads"

router = APIRouter()


# ---------------------------------------------------------------------------
# Background processing task
# ---------------------------------------------------------------------------

async def _process_document(
    document_id: str,
    filename: str,
    dest_path: str,
    is_diagram: bool,
    workspace: str,
    user_id: int,
):
    """
    Runs the heavy OCR / embedding / vision work in the background.
    Opens its own DB session (BackgroundTasks runs after the request
    context is torn down, so we cannot reuse the request-scoped session).
    Updates the document_status row when done.
    """
    db: Session = SessionLocal()
    try:
        status_row = db.query(DocumentStatus).filter(
            DocumentStatus.document_id == document_id
        ).first()

        is_docx = filename.lower().endswith(".docx")
        is_xlsx = filename.lower().endswith(".xlsx")
        is_xls = filename.lower().endswith(".xls") and not is_xlsx
        is_image = filename.lower().endswith((".jpg", ".jpeg", ".png"))

        ocr_used = False
        diagram_mode = False
        avg_ocr_confidence = None
        vision_description_length = 0
        parsed_doc = None

        if is_xlsx:
            print(f"[BG] Calling extract_text_xlsx on {dest_path}")
            parsed_doc = extract_text_xlsx(dest_path, document_id, filename)
        elif is_xls:
            print(f"[BG] Calling extract_text_xls on {dest_path}")
            parsed_doc = extract_text_xls(dest_path, document_id, filename)
        elif is_docx:
            print(f"[BG] Calling extract_text_docx on {dest_path}")
            parsed_doc = extract_text_docx(dest_path, document_id, filename)
        elif is_image:
            print(f"[BG] Calling extract_text_image on {dest_path}, is_diagram={is_diagram}")
            parsed_doc = await extract_text_image(dest_path, document_id, filename, is_diagram=is_diagram)
            ocr_used = True
            avg_ocr_confidence = float(parsed_doc["metadata"].get("avg_ocr_confidence", 0.0))
            if is_diagram:
                diagram_mode = True
                vision_description_length = int(parsed_doc["metadata"].get("vision_description_length", 0))
        else:
            print(f"[BG] Calling is_scanned on {dest_path}")
            scanned = is_scanned(dest_path)
            print(f"[BG] is_scanned returned: {scanned}")
            if scanned:
                print(f"[BG] Calling ocr_scanned_pdf on {dest_path}")
                parsed_doc = await ocr_scanned_pdf(dest_path, document_id, filename, is_diagram=is_diagram)
                print(f"[BG] ocr_scanned_pdf completed.")
                ocr_used = True
                avg_ocr_confidence = float(parsed_doc["metadata"].get("avg_ocr_confidence", 0.0))
                if is_diagram:
                    diagram_mode = True
                    vision_description_length = int(parsed_doc["metadata"].get("vision_description_length", 0))
            else:
                parsed_doc = extract_text_pymupdf(dest_path, document_id, filename)

        # Chunk, embed, and persist
        pages = serialize_document(parsed_doc)
        text_chunks = chunk_text(pages)
        for tc in text_chunks:
            tc["chunk_source"] = "ocr" if ocr_used else "text"

        vision_texts = parsed_doc["metadata"].get("vision_texts", []) if parsed_doc and "metadata" in parsed_doc else []
        vision_chunks_raw = []
        for vt in vision_texts:
            vision_chunks_raw.append({
                "page": vt.get("page", 1),
                "text": vt.get("text", ""),
                "ocr_confidence": vt.get("ocr_confidence")
            })
            
        vision_chunks_chunked = chunk_text(vision_chunks_raw)
        for vc in vision_chunks_chunked:
            vc["chunk_source"] = "vision_description"

        chunks = []
        all_pages = sorted(list(set([c["page"] for c in text_chunks] + [vc["page"] for vc in vision_chunks_chunked])))
        for p in all_pages:
            p_text = [c for c in text_chunks if c["page"] == p]
            p_vision = [vc for vc in vision_chunks_chunked if vc["page"] == p]
            
            conf = None
            if p_vision:
                conf = p_vision[0].get("ocr_confidence")
            elif p_text:
                conf = p_text[0].get("ocr_confidence")

            if conf is not None and conf < 60.0:
                chunks.extend(p_vision)
                chunks.extend(p_text)
            else:
                chunks.extend(p_text)
                chunks.extend(p_vision)

        chunks_created = 0
        for chunk in chunks:
            chunk_content = chunk["text"]
            try:
                embedding = await gateway.embed(chunk_content)
            except Exception as e:
                print(f"[BG] Embedding failed for chunk on page {chunk['page']}, retrying truncated. Error: {e}")
                chunk_content = chunk_content[:800]
                try:
                    embedding = await gateway.embed(chunk_content)
                except Exception as e2:
                    print(f"[BG] Embedding failed again for document {document_id}. Marking as failed. Error: {e2}")
                    if status_row:
                        status_row.status = "failed"
                        status_row.error_message = f"Failed to embed chunk: {str(e2)}"
                        status_row.updated_at = datetime.utcnow()
                        db.commit()
                    return  # Early exit, upload failed
            
            doc_chunk = DocumentChunk(
                document_id=document_id,
                filename=filename,
                page=chunk["page"],
                text=chunk_content,
                embedding=embedding,
                workspace=workspace,
                ocr_confidence=chunk.get("ocr_confidence"),
                chunk_source=chunk.get("chunk_source", "text"),
            )
            db.add(doc_chunk)
            chunks_created += 1

        db.commit()

        # Audit log (recreate user reference by id)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            log_action(
                db=db,
                user=user,
                action="diagram_upload" if diagram_mode else "document_upload",
                resource=filename,
                details={
                    "document_id": document_id,
                    "chunks_created": chunks_created,
                    "ocr_used": ocr_used,
                    "diagram_mode": diagram_mode,
                    "vision_description_length": vision_description_length,
                },
            )

        # Mark completed
        if status_row:
            status_row.status = "completed"
            status_row.updated_at = datetime.utcnow()
            db.commit()
        print(f"[BG] {document_id}: processing completed — {chunks_created} chunks")

    except Exception as exc:
        traceback.print_exc()
        db.rollback()
        # Mark failed
        try:
            status_row = db.query(DocumentStatus).filter(
                DocumentStatus.document_id == document_id
            ).first()
            if status_row:
                status_row.status = "failed"
                status_row.error_message = str(exc)
                status_row.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        print(f"[BG] {document_id}: processing FAILED — {exc}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Upload endpoint — returns immediately with document_id + "processing"
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ACL helpers
# ---------------------------------------------------------------------------

def _build_acl_subqueries(user: User):
    """
    Returns (restricted_sq, allowed_sq) scalar subqueries for document_id.

    restricted_sq  — document_ids that have at least one ACL entry.
    allowed_sq     — document_ids the given user is explicitly allowed into.
    """
    restricted_sq = select(DocumentAcl.document_id).distinct().scalar_subquery()
    allowed_sq = (
        select(DocumentAcl.document_id)
        .where(
            or_(
                DocumentAcl.user_id == user.id,
                DocumentAcl.role == user.role,
            )
        )
        .scalar_subquery()
    )
    return restricted_sq, allowed_sq


def _apply_acl_filter(query, id_column, user: User, is_document_status=True):
    """
    Applies document-level ACL filter to *query* using *id_column*
    (DocumentStatus.document_id or DocumentChunk.document_id).

    Admins bypass ACL entirely.
    """
    if user.role == "admin":
        return query  # admins see everything

    restricted_sq, allowed_sq = _build_acl_subqueries(user)
    
    conditions = [
        id_column.notin_(restricted_sq),  # document has no ACL → open
        id_column.in_(allowed_sq),         # document has ACL and user matches
    ]
    
    if is_document_status:
        # If querying DocumentStatus, allow access if user is the uploader
        conditions.append(DocumentStatus.uploader_id == user.id)

    return query.filter(or_(*conditions))


@router.get("/", response_model=List[DocumentInfoResponse])
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    query = db.query(DocumentStatus).order_by(desc(DocumentStatus.created_at))
    if current_user.role != "admin":
        query = query.filter(DocumentStatus.workspace == current_user.workspace)

    # Apply document-level ACL filter
    query = _apply_acl_filter(query, DocumentStatus.document_id, current_user)

    docs = query.all()

    # Build set of restricted doc_ids for badge annotation
    restricted_ids = {
        row[0]
        for row in db.execute(
            select(DocumentAcl.document_id).distinct()
        ).fetchall()
    }

    results = []
    for doc in docs:
        ext = os.path.splitext(doc.filename)[1].lower() if doc.filename else ""
        results.append(DocumentInfoResponse(
            document_id=doc.document_id,
            filename=doc.filename,
            file_type=ext[1:].upper() if ext else "UNKNOWN",
            status=doc.status,
            workspace=doc.workspace,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            is_restricted=(doc.document_id in restricted_ids),
        ))
    return results


# ---------------------------------------------------------------------------
# ACL management endpoints
# ---------------------------------------------------------------------------

from pydantic import BaseModel as PydanticModel
from typing import Optional as Opt

class AclEntryRequest(PydanticModel):
    user_id: Opt[int] = None
    role: Opt[str] = None

class AclEntryResponse(PydanticModel):
    id: int
    document_id: str
    user_id: Opt[int]
    role: Opt[str]

    class Config:
        from_attributes = True


@router.get("/{document_id}/acl", response_model=List[AclEntryResponse])
def get_document_acl(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Return current ACL entries for a document."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager required.")
    return db.query(DocumentAcl).filter(DocumentAcl.document_id == document_id).all()


@router.post("/{document_id}/acl", response_model=AclEntryResponse)
def grant_document_acl(
    document_id: str,
    payload: AclEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Grant ACL access to a user or role."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager required.")

    if payload.user_id is None and payload.role is None:
        raise HTTPException(
            status_code=400,
            detail="Must specify either user_id or role."
        )

    # Check if exists
    existing = db.query(DocumentAcl).filter(
        DocumentAcl.document_id == document_id,
        DocumentAcl.user_id == payload.user_id,
        DocumentAcl.role == payload.role
    ).first()
    
    if existing:
        return existing

    row = DocumentAcl(
        document_id=document_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    target = f"user {payload.user_id}" if payload.user_id else f"role {payload.role}"
    log_action(db, current_user, "acl_granted", "document",
               {"document_id": document_id, "target": target})
    return row


@router.delete("/{document_id}/acl/{acl_id}", status_code=204)
def revoke_document_acl(
    document_id: str,
    acl_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Revoke a specific ACL entry."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager required.")
        
    entry = db.query(DocumentAcl).filter(DocumentAcl.id == acl_id, DocumentAcl.document_id == document_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="ACL entry not found.")
        
    target = f"user {entry.user_id}" if entry.user_id else f"role {entry.role}"
    db.delete(entry)
    db.commit()
    
    log_action(db, current_user, "acl_revoked", "document",
               {"document_id": document_id, "target": target})




# ---------------------------------------------------------------------------
# Knowledge Base summary endpoint
# ---------------------------------------------------------------------------

@router.get("/knowledge-base", response_model=List[KnowledgeBaseSummary])
def get_knowledge_base(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Return per-workspace document counts and last_updated timestamps."""
    workspaces = db.query(Workspace).order_by(Workspace.name).all()
    results = []
    for ws in workspaces:
        query = db.query(DocumentStatus).filter(DocumentStatus.workspace == ws.name)
        if current_user.role != "admin":
            query = _apply_acl_filter(query, DocumentStatus.document_id, current_user)
            
        doc_count = query.count()
        last_row = query.order_by(desc(DocumentStatus.updated_at)).first()
        results.append(KnowledgeBaseSummary(
            workspace_name=ws.name,
            document_count=doc_count,
            last_updated=last_row.updated_at if last_row else None,
        ))
    return results


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------

@router.get("/workspaces", response_model=List[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Return all available workspaces."""
    return db.query(Workspace).order_by(Workspace.name).all()


from pydantic import BaseModel as PydanticBaseModel

class WorkspaceCreate(PydanticBaseModel):
    name: str


@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """Create a new named workspace/knowledge-base category."""
    name = payload.name.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Workspace name cannot be empty.")
    existing = db.query(Workspace).filter(Workspace.name == name).first()
    if existing:
        return existing
    ws = Workspace(name=name)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


# ---------------------------------------------------------------------------
# Upload endpoint — returns immediately with document_id + "processing"
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    is_diagram: bool = Form(False),
    workspace: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    document_id = str(uuid.uuid4())
    filename = file.filename or "unknown"
    dest_path = os.path.join(UPLOAD_DIR, f"{document_id}_{filename}")

    # --- Phase 1: save file synchronously (fast) ---
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    finally:
        file.file.close()

    # Calculate hash to detect duplicates
    file_hash = hashlib.sha256()
    with open(dest_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            file_hash.update(chunk)
    file_hash_hex = file_hash.hexdigest()

    # Resolve workspace: client-supplied > user's own > "general"
    user_workspace = current_user.workspace or "general"
    resolved_workspace = (workspace.strip().lower() if workspace and workspace.strip() else None) or user_workspace
    
    if current_user.role != "admin" and resolved_workspace != user_workspace:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=403, detail="Non-admin users can only upload to their own workspace.")

    # Check for duplicates in the same workspace that are completed
    existing_query = db.query(DocumentStatus).filter(
        DocumentStatus.file_hash == file_hash_hex,
        DocumentStatus.workspace == resolved_workspace,
        DocumentStatus.status == "completed"
    )
    # Only match documents the user is allowed to see
    existing_query = _apply_acl_filter(existing_query, DocumentStatus.document_id, current_user)
    existing = existing_query.first()
    
    if existing:
        os.remove(dest_path)
        print(f"[UPLOAD] Duplicate detected: {filename} matches existing doc {existing.document_id}")
        return {
            "document_id": existing.document_id,
            "filename": existing.filename,
            "status": "duplicate",
        }

    print(f"[UPLOAD] File saved: {filename} → {dest_path}")

    # Insert status row immediately so polling can start
    status_row = DocumentStatus(
        document_id=document_id,
        filename=filename,
        file_hash=file_hash_hex,
        workspace=resolved_workspace,
        uploader_id=current_user.id,
        status="processing",
    )
    db.add(status_row)
    db.commit()

    # --- Phase 2: schedule heavy work (async, non-blocking) ---
    background_tasks.add_task(
        _process_document,
        document_id=document_id,
        filename=filename,
        dest_path=dest_path,
        is_diagram=is_diagram,
        workspace=resolved_workspace,
        user_id=current_user.id,
    )

    # Return immediately
    return {
        "document_id": document_id,
        "filename": filename,
        "status": "processing",
    }


# ---------------------------------------------------------------------------
# Status polling endpoint
# ---------------------------------------------------------------------------

@router.get("/{document_id}/status")
def get_document_status(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the current processing status for a document.
    Status values: "processing" | "completed" | "failed"
    """
    query = db.query(DocumentStatus).filter(DocumentStatus.document_id == document_id)
    if current_user.role != "admin":
        query = _apply_acl_filter(query, DocumentStatus.document_id, current_user)
        
    status_row = query.first()
    if not status_row:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
    return {
        "document_id": document_id,
        "filename": status_row.filename,
        "status": status_row.status,
        "error_message": status_row.error_message,
        "created_at": status_row.created_at.isoformat() if status_row.created_at else None,
        "updated_at": status_row.updated_at.isoformat() if status_row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Duplicates endpoint
# ---------------------------------------------------------------------------

@router.get("/duplicates")
def get_duplicates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """
    Admin-only: Returns a list of duplicate document groups based on file_hash.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required.")
        
    from sqlalchemy import func
    
    log_action(db, current_user, "view_duplicates", "documents", {})
    
    duplicate_hashes = db.query(DocumentStatus.file_hash, DocumentStatus.workspace).filter(
        DocumentStatus.file_hash.isnot(None)
    ).group_by(DocumentStatus.file_hash, DocumentStatus.workspace).having(
        func.count(DocumentStatus.id) > 1
    ).all()
    
    results = []
    for h, ws in duplicate_hashes:
        docs = db.query(DocumentStatus).filter(
            DocumentStatus.file_hash == h,
            DocumentStatus.workspace == ws
        ).all()
        results.append({
            "file_hash": h,
            "workspace": ws,
            "documents": [
                {"document_id": d.document_id, "filename": d.filename, "created_at": d.created_at.isoformat() if d.created_at else None}
                for d in docs
            ]
        })
    return results

# ---------------------------------------------------------------------------
# Download endpoint for generated files (unchanged)
# ---------------------------------------------------------------------------

GENERATED_DIR = "/app/uploads/generated"


@router.get("/download/{filename}")
def download_generated_document(
    filename: str,
    db: Session = Depends(get_db),
    token: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Serves a generated file (.docx, .xlsx, .pdf, .pptx) from
    /app/uploads/generated/ as a downloadable attachment.
    Accepts auth via Bearer header OR ?token= query param.
    """
    if current_user is None:
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            current_user = db.query(User).filter(User.email == email).first()
            if current_user is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
        except JWTError:
            raise HTTPException(status_code=401, detail="Not authenticated")

    # Sanitise: reject any path traversal attempts
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine mime type from extension
    if filename.lower().endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.lower().endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.lower().endswith(".pptx"):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Document delete endpoint — removes ACLs, chunks, status row, and file
# ---------------------------------------------------------------------------

@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("documents.manage")),
):
    """
    Permanently delete a document and all associated data:
    - document_acl rows (ACL cleanup)
    - document_chunks rows (RAG cleanup)
    - document_status row
    - the uploaded file on disk (if present)

    Only the uploader or an admin/manager may delete.
    """
    status_row = db.query(DocumentStatus).filter(
        DocumentStatus.document_id == document_id
    ).first()

    if not status_row:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Permission check: uploader or admin/manager
    is_uploader = status_row.uploader_id == current_user.id
    is_privileged = current_user.role in ("admin", "manager")
    if not is_uploader and not is_privileged:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this document.")

    # 1. Delete ACL entries
    db.query(DocumentAcl).filter(DocumentAcl.document_id == document_id).delete()

    # 2. Delete all chunks
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

    # 3. Delete status row
    filename = status_row.filename
    db.delete(status_row)
    db.commit()

    # 4. Delete the uploaded file from disk (best-effort)
    try:
        upload_dir = "/app/uploads"
        for entry in os.listdir(upload_dir):
            if entry.startswith(document_id):
                os.remove(os.path.join(upload_dir, entry))
                break
    except Exception:
        pass  # File already gone or inaccessible — non-fatal

    log_action(db, current_user, "document_deleted", "document",
               {"document_id": document_id, "filename": filename})
