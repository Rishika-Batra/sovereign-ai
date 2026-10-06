import re
import asyncio
from app.ai_gateway.gateway import gateway

STRONG_CODE_KEYWORDS = {
    "bug", "compile", "syntax", "python", "javascript", "typescript",
    "def", "html", "css", "react", "fastapi",
}
WEAK_CODE_KEYWORDS = {"error", "function", "class", "code", "import"}

VISION_KEYWORDS = {"image", "picture", "photo", "diagram", "screenshot", "visual"}
DOCUMENT_KEYWORDS = {
    "pdf", "document", "file", "word", "excel", "spreadsheet",
    "presentation", "report", "inspection", "summary",
}


async def route_task(message: str) -> str:
    """
    Analyzes an incoming user message for task signals (keywords, syntax).
    If ambiguous, uses an LLM to classify.
    """
    if not message:
        return "general"

    strong_matches = set()
    weak_only = False

    words = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", message.lower()))

    # Coding: strong signal from code fences or strong keywords
    has_code_fence = "```" in message
    has_strong_code = not words.isdisjoint(STRONG_CODE_KEYWORDS)
    has_weak_code = not words.isdisjoint(WEAK_CODE_KEYWORDS)

    if has_code_fence or has_strong_code:
        strong_matches.add("coding")
    elif has_weak_code:
        weak_only = True

    if not words.isdisjoint(VISION_KEYWORDS):
        strong_matches.add("vision")
    if not words.isdisjoint(DOCUMENT_KEYWORDS):
        strong_matches.add("document")

    # Zero strong matches and no weak coding -> general
    if len(strong_matches) == 0 and not weak_only:
        print("[ROUTER] Route decided by heuristic: general")
        return "general"

    # Exactly one strong match and no weak ambiguity -> use it
    if len(strong_matches) == 1 and not weak_only:
        route = next(iter(strong_matches))
        print(f"[ROUTER] Route decided by heuristic: {route}")
        return route

    # Ambiguous (weak coding alone, or multiple strong matches): ask LLM
    all_candidates = strong_matches | ({"coding"} if weak_only else set())
    try:
        from app.ai_gateway.registry import get_model_name
        model_name = get_model_name("general")
        
        prompt = (
            "Classify the following task into exactly one of these categories: general, coding, vision, document. "
            "Reply with only the one-word category name, nothing else.\n\n"
            f"Task: {message}"
        )
        response = await asyncio.wait_for(
            gateway.chat(model_name, [{"role": "user", "content": prompt}]),
            timeout=5.0
        )
        predicted = re.sub(r'[^a-z]', '', response.strip().lower())
        
        if predicted in {"general", "coding", "vision", "document"}:
            print(f"[ROUTER] Route decided by LLM: {predicted}")
            return predicted
        else:
            print(f"[ROUTER] LLM returned invalid category '{predicted}'. Falling back to heuristic.")
            return next((p for p in ["vision", "document", "coding"] if p in all_candidates), "general")
    except Exception as e:
        print(f"[ROUTER] LLM routing failed/timeout: {e}. Falling back to heuristic.")
        return next((p for p in ["vision", "document", "coding"] if p in all_candidates), "general")

