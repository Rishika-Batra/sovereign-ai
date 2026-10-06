from typing import List, Dict, Any
from .providers.ollama_provider import OllamaProvider

class AIGateway:
    def __init__(self):
        # We instantiate the underlying provider here.
        # This keeps the abstraction clean so other modules only use gateway.
        self._provider = OllamaProvider()

    async def chat(self, model: str, messages: List[Dict[str, str]]) -> str:
        return await self._provider.chat(model, messages)

    async def embed(self, text: str) -> List[float]:
        return await self._provider.embed(text)

    async def vision(self, model: str, image_b64: str, prompt: str, options: dict = None) -> str:
        return await self._provider.vision(model, image_b64, prompt, options=options)

# Export a single gateway instance for the rest of the application
gateway = AIGateway()
