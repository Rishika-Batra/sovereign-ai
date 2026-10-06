import os
import httpx
import asyncio
from typing import List, Dict, Any
from app.ai_gateway.registry import get_model_name

async def _with_retries(coro_func, max_retries=3, base_delay=2.0):
    """Simple retry wrapper with exponential backoff for intermittent API errors."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await coro_func()
        except httpx.HTTPError as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[OllamaProvider] API error: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
    raise last_exc

class OllamaProvider:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", get_model_name("embedding"))

    async def chat(self, model: str, messages: List[Dict[str, str]]) -> str:
        async def _call():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "num_ctx": 4096
                        }
                    },
                    timeout=None
                )
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "")
        return await _with_retries(_call)

    async def embed(self, text: str) -> List[float]:
        async def _call():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.embed_model,
                        "prompt": text
                    },
                    timeout=None
                )
                response.raise_for_status()
                return response.json().get("embedding", [])
        return await _with_retries(_call)

    async def vision(self, model: str, image_b64: str, prompt: str, options: dict = None) -> str:
        async def _call():
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False
                }
                if options:
                    payload["options"] = options
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=None
                )
                response.raise_for_status()
                return response.json().get("response", "")
        return await _with_retries(_call)
