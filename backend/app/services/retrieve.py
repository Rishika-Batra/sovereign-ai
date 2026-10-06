import time
from typing import List, Dict
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from app.db.models import User, DocumentChunk
from app.ai_gateway.gateway import gateway


async def retrieve_context(
    db: Session,
    query: str,
    user: User,
    top_k: int = 5,
    filenames: List[str] = None,
) -> List[Dict]:
    """
    Embeds the query, performs pgvector cosine similarity search filtered by the
    user's workspace and optional filenames, and returns top_k matching chunks.
    """
    t0 = time.time()
    query_embedding = await gateway.embed(query)
    print(f"[TIMING] embed_query: {time.time() - t0:.2f}s")
    
    t1 = time.time()
    user_workspace = user.workspace if user and user.workspace else "general"

    from sqlalchemy import or_, and_, select
    from app.db.models import DocumentAcl, DocumentStatus

    # Strict SQL-level workspace isolation via WHERE clause filter
    # Also exclude vision-source chunks (screenshot OCR hallucinations are unreliable)
    # Plus ACL filtering:
    # 1. No ACL rows for the document
    # 2. OR an ACL row matches user_id or role
    # 3. OR the user is an admin
    # 4. OR the user is the uploader
    
    base_query = (
        db.query(DocumentChunk)
        .join(DocumentStatus, DocumentChunk.document_id == DocumentStatus.document_id, isouter=True)
        .filter(DocumentChunk.workspace == user_workspace)
        .filter(DocumentChunk.chunk_source != "vision")
    )
    
    if user.role != "admin":
        acl_exists = select(DocumentAcl.id).where(DocumentAcl.document_id == DocumentChunk.document_id).exists()
        acl_matches = select(DocumentAcl.id).where(
            and_(
                DocumentAcl.document_id == DocumentChunk.document_id,
                or_(DocumentAcl.user_id == user.id, DocumentAcl.role == user.role)
            )
        ).exists()
        
        base_query = base_query.filter(
            or_(
                ~acl_exists,
                acl_matches,
                DocumentStatus.uploader_id == user.id
            )
        )

    if filenames:
        base_query = base_query.filter(DocumentChunk.filename.in_(filenames))

    # Exact keyword match fallback for short ID-like queries (e.g., "M-104")
    exact_chunks = []
    if len(query) < 20:
        exact_results = base_query.filter(DocumentChunk.text.ilike(f"%{query}%")).limit(3).all()
        exact_chunks = [(c, 0.0) for c in exact_results]

    vector_results = (
        base_query.add_columns(DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"))
        .filter(DocumentChunk.embedding.cosine_distance(query_embedding) < 0.55)
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(30)
        .all()
    )
    
    # Combine uniquely
    seen_ids = set()
    combined_chunks = []
    for c, dist in exact_chunks + vector_results:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            combined_chunks.append((c, dist))
    print(f"[TIMING] vector_search: {time.time() - t1:.2f}s")
    
    if not combined_chunks:
        return []

    t2 = time.time()
    
    # Reranking: count chunks per document to apply small document boost
    from sqlalchemy import func
    import math
    import re
    
    doc_ids = list(set([c.document_id for c, _ in combined_chunks]))
    doc_chunk_counts = dict(
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .filter(DocumentChunk.document_id.in_(doc_ids))
        .group_by(DocumentChunk.document_id)
        .all()
    )
    
    STOPWORDS = {"the", "and", "for", "with", "this", "that", "are", "was", "were", "you", "not", "have", "has", "had", "but", "all", "any", "one", "can", "from", "what", "how", "why", "who"}
    query_words = {
        w for w in re.findall(r'[a-zA-Z0-9]+', query.lower()) 
        if len(w) >= 3 and w not in STOPWORDS
    }
    
    scored_chunks = []
    for c, dist in combined_chunks:
        sim = 1.0 - (dist if dist is not None else 1.0)
        chunk_words = set(re.findall(r'[a-zA-Z0-9]+', c.text.lower()))
        overlap = sum(1 for w in query_words if w in chunk_words)
        overlap_score = overlap * 0.05
        
        doc_count = doc_chunk_counts.get(c.document_id, 1)
        doc_boost = 0.2 / math.log2(doc_count + 1) if doc_count > 0 else 0.0
        
        score = sim + overlap_score + doc_boost
        scored_chunks.append((score, c))
        
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    
    # Apply diversity: max 3 chunks per document and skip duplicates
    chunks = []
    doc_usage = {}
    seen_texts = set()
    for score, c in scored_chunks:
        if doc_usage.get(c.document_id, 0) >= 3:
            continue
            
        norm_text = " ".join(c.text.lower().split())
        if norm_text in seen_texts:
            continue
        seen_texts.add(norm_text)
        
        chunks.append(c)
        doc_usage[c.document_id] = doc_usage.get(c.document_id, 0) + 1
        if len(chunks) >= top_k:
            break
            
    print(f"[TIMING] rerank: {time.time() - t2:.2f}s")

    results = []
    for chunk in chunks:
        results.append(
            {
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "page": chunk.page,
                "text": chunk.text,
                "ocr_confidence": chunk.ocr_confidence,
            }
        )

    return results
