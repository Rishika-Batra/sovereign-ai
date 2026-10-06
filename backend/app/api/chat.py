import time
import base64
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session

from app.db.models import User, ChatSession, Message
from app.api.deps import get_db, get_current_user
from app.api.schemas import ChatResponse, SessionResponse, MessageResponse, SourceInfo
from app.ai_gateway.gateway import gateway
from app.ai_gateway.router import route_task
from app.ai_gateway.registry import get_model_name
from app.services.retrieve import retrieve_context
from app.services.audit import log_action

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(...),
    image: Optional[UploadFile] = File(None),
    session_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if session_id:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to access this session")
    else:
        # Create a new session
        title = message[:50] + "..." if len(message) > 50 else message
        session = ChatSession(user_id=current_user.id, title=title)
        db.add(session)
        db.commit()
        db.refresh(session)

    # Save raw user message to DB (keeps chat history clean)
    user_message = Message(session_id=session.id, role="user", content=message)
    db.add(user_message)
    db.commit()

    # Check if an image was uploaded for vision processing
    if image and image.filename:
        task_key = "vision"
        model_name = get_model_name(task_key)
        image_bytes = await image.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        reply_content = await gateway.vision(model_name, image_b64, message)
        sources = []
    else:
        # Extract metadata filters like @filename
        extracted_filenames = re.findall(r'@([a-zA-Z0-9_.-]+)', message)
        clean_message = re.sub(r'@([a-zA-Z0-9_.-]+)', '', message).strip()
        if not clean_message:
            clean_message = message
            
        # Perform RAG retrieval (isolated by user workspace)
        retrieved_chunks = await retrieve_context(
            db, 
            clean_message, 
            user=current_user, 
            filenames=extracted_filenames if extracted_filenames else None
        )

        sources = []
        seen_sources = set()
        for chunk in retrieved_chunks:
            source_key = (chunk["filename"], chunk["page"])
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                sources.append(SourceInfo(filename=chunk["filename"], page=chunk["page"]))

        # Build augmented prompt for the model
        t_build_start = time.time()
        OCR_HEDGE_THRESHOLD = 85.0
        if retrieved_chunks:
            context_parts = []
            for c in retrieved_chunks:
                header = f"[Source: {c['filename']}, Page {c['page']}]"
                ocr_conf = c.get("ocr_confidence")
                if ocr_conf is not None and ocr_conf < OCR_HEDGE_THRESHOLD:
                    hedge = f"(OCR confidence: {ocr_conf:.0f}% — verify against source)\n"
                else:
                    hedge = ""
                context_parts.append(f"{header}\n{hedge}{c['text']}")
            context_str = "\n\n".join(context_parts)
            augmented_prompt = (
                f"You are a helpful AI assistant with access to the following retrieved context documents:\n\n"
                f"{context_str}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Answer using the provided context. Quote exact figures, names, and table cells from the context rather than summarizing them loosely.\n"
                f"2. Cite the filename and page number for every fact taken from the context.\n"
                f"3. If the question is about the documents and the needed value is not in the context, say \"not found in the provided documents\". Do not guess.\n"
                f"4. Never describe code that would compute a value instead of stating the value. Only if the question is clearly general and unrelated to the documents may you use general knowledge.\n"
                f"A value is a number or text that appears as a result (for example a printed output, a table cell, or a sentence stating it). Source code that would print or compute a value is NOT the value.\n"
                f"Example: if the context only contains code like print('Test MAE:', mae) but no actual number, the correct answer is: not found in the provided documents.\n\n"
                f"User Question: {message}"
            )
        else:
            augmented_prompt = message
        print(f"[TIMING] build_context: {time.time() - t_build_start:.2f}s")

        # Route message to appropriate model via AI Gateway registry
        task_key = await route_task(message)
        
        # If routed to vision but we are doing text-based RAG, use the general model for synthesis
        if task_key == "vision":
            model_name = get_model_name("general")
            # Keep task_key as "vision" for UI badge rendering
        else:
            model_name = get_model_name(task_key)

        # Call AI gateway with routed model
        print(f"[TIMING] prompt_length_chars: {len(augmented_prompt)}")
        t_llm_start = time.time()
        reply_content = await gateway.chat(
            model_name,
            [{"role": "user", "content": augmented_prompt}]
        )
        print(f"[TIMING] llm_generate: {time.time() - t_llm_start:.2f}s")

    # Save assistant message
    assistant_message = Message(session_id=session.id, role="assistant", content=reply_content)
    db.add(assistant_message)
    db.commit()

    log_action(
        db=db,
        user=current_user,
        action="chat_message",
        resource=f"session_{session.id}",
        details={"model_used": task_key, "session_id": session.id},
    )

    return ChatResponse(
        session_id=session.id,
        reply=reply_content,
        sources=sources,
        model_used=task_key,
    )


@router.get("/sessions", response_model=List[SessionResponse])
def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).order_by(ChatSession.created_at.desc()).all()
    return sessions


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this session")

    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at.asc()).all()
    return messages
