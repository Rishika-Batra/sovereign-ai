from collections import Counter
import math

def heuristic_score(distance, text, query, doc_chunk_count):
    sim = 1.0 - distance
    
    query_words = set(query.lower().split())
    text_lower = text.lower()
    overlap = sum(1 for w in query_words if w in text_lower)
    overlap_score = overlap * 0.05
    
    # Boost for smaller documents (fewer chunks)
    # e.g., 1 chunk -> 0.1 boost, 100 chunks -> 0.01 boost
    doc_boost = 0.1 / math.log2(doc_chunk_count + 1)
    
    return sim + overlap_score + doc_boost

print(heuristic_score(0.2, "This is a test document", "test", 1))
