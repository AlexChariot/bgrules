"""Helpers for interacting with the local Ollama instance."""

import requests

from bgrules import config


def _tags_url() -> str:
    return f"{config.OLLAMA_BASE_URL}/api/tags"


def is_ollama_running(timeout: int = 2) -> bool:
    """Return True when the local Ollama HTTP API is reachable."""
    try:
        response = requests.get(_tags_url(), timeout=timeout)
        response.raise_for_status()
        return True
    except Exception:
        return False


def get_available_models() -> list[str]:
    """Return the list of models currently available in the local Ollama instance."""
    try:
        response = requests.get(_tags_url(), timeout=5)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []


def ensure_ollama_running() -> None:
    """Raise a clear error if Ollama is not reachable."""
    if is_ollama_running():
        return

    raise RuntimeError(
        "Ollama n'est pas détecté sur http://localhost:11434. "
        "Lance-le avec `ollama serve`, puis réessaie."
    )


def _model_matches(required: str, available_name: str) -> bool:
    """Return True if *available_name* satisfies *required*.

    Ollama often reports tagged names such as ``llama3:latest`` while the
    configured model may be ``llama3``. We accept both exact matches and
    base-name matches ignoring the tag.
    """
    if required == available_name:
        return True
    return available_name.split(":", 1)[0] == required.split(":", 1)[0]


def ensure_required_models_available() -> None:
    """Raise a clear error if Ollama is running but the configured models are missing."""
    ensure_ollama_running()
    available = get_available_models()

    missing: list[str] = []
    if not any(_model_matches(config.LLM_MODEL, name) for name in available):
        missing.append(config.LLM_MODEL)
    if not any(_model_matches(config.EMBEDDINGS_MODEL, name) for name in available):
        missing.append(config.EMBEDDINGS_MODEL)

    if not missing:
        return

    deduped = []
    for model in missing:
        if model not in deduped:
            deduped.append(model)

    pull_commands = " ; ".join(f"ollama pull {model}" for model in deduped)
    raise RuntimeError(
        "Ollama est lancé, mais le ou les modèles requis sont absents: "
        f"{', '.join(deduped)}. "
        f"Installe-les avec: {pull_commands}"
    )


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
        "ollama_reachable": is_ollama_running(),
        "llm_available": any(_model_matches(config.LLM_MODEL, name) for name in available),
        "embeddings_available": any(_model_matches(config.EMBEDDINGS_MODEL, name) for name in available),
    }
