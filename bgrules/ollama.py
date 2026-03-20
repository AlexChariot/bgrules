"""Helpers for interacting with the local Ollama instance."""

import requests

from bgrules import config


def get_available_models() -> list[str]:
    """Return the list of models currently available in the local Ollama instance."""
    try:
        response = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []


def get_current_llm_model() -> str:
    """Return the currently configured LLM model."""
    return config.LLM_MODEL


def get_current_embeddings_model() -> str:
    """Return the currently configured embeddings model."""
    return config.EMBEDDINGS_MODEL


def set_llm_model(model: str) -> None:
    """Override LLM_MODEL at runtime (does not persist to disk)."""
    config.LLM_MODEL = model


def set_embeddings_model(model: str) -> None:
    """Override EMBEDDINGS_MODEL at runtime (does not persist to disk).

    Warning: the FAISS index must be cleared and rebuilt after this change.
    """
    config.EMBEDDINGS_MODEL = model


def select_best_available_model(preferred: list[str] | None = None) -> str | None:
    """Pick the best available model from Ollama, using an optional preference list.

    If *preferred* is provided, the first model in the list that is available
    is returned. If none match, the first available model is returned as a
    fallback. Returns None if Ollama has no models at all.
    """
    available = get_available_models()
    if not available:
        return None

    if preferred:
        for p in preferred:
            for a in available:
                if a.startswith(p):   # e.g. "llama3" matches "llama3:8b"
                    return a

    return available[0]


def model_status() -> dict:
    """Return a status dict with current config and Ollama availability."""
    available = get_available_models()
    return {
        "llm_model": config.LLM_MODEL,
        "embeddings_model": config.EMBEDDINGS_MODEL,
        "available_models": available,
        "ollama_reachable": bool(available),
        "llm_available": config.LLM_MODEL in available,
        "embeddings_available": config.EMBEDDINGS_MODEL in available,
    }