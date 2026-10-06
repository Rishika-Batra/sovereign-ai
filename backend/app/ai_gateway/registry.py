from typing import Dict, Any

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "general": {
        "name": "llama3.1:8b",
        "type": "general",
        "backend": "ollama",
    },
    "coding": {
        "name": "qwen2.5-coder:7b",
        "type": "coding",
        "backend": "ollama",
    },
    "vision": {
        "name": "llava:7b",
        "type": "vision",
        "backend": "ollama",
    },
    "document": {
        "name": "llama3.1:8b",
        "type": "general",
        "backend": "ollama",
    },
    "embedding": {
        "name": "nomic-embed-text",
        "type": "embedding",
        "backend": "ollama",
    },
}

def get_model_name(key: str) -> str:
    """
    Returns the underlying model name for a registry task key.
    Defaults to 'general' model if the key is not in MODEL_REGISTRY.
    """
    model_info = MODEL_REGISTRY.get(key, MODEL_REGISTRY["general"])
    return model_info["name"]
