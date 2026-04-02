import os
import sys


def is_debug_mode() -> bool:
    """Return True when debug output is enabled for the current process."""
    return "--debug" in sys.argv

ALLOWED_DOMAINS = [
    # Éditeurs majeurs
    "asmodee",
    "days-of-wonder",
    "ravensburger",
    "hasbro",
    "zmangames",
    "fantasyflightgames",
    "cephalofair",        # Gloomhaven
    "stonemaiergames",    # Scythe, Wingspan
    "czechgames",         # CGE
    "plaidhatgames",
    "alderac",            # AEG
    "wizkids",
    "kosmogames",
    "iello",
    "luckyduckgames",
    "matagot",
    "spacecowboys",       # Splendor, Time Stories
    "feuerland",
    "hobbylarp",

    # Agrégateurs / ressources de règles
    "1j1ju",              # cdn.1j1ju.com — source principale FR
    "boardgamegeek",
    "ultraboardgames",
    "officialgamerules",
    "gmtgames",
    "riograndegames",
]

PDF_FOLDER = "data/pdfs"
DB_PATH = "sqlite:///data/db.sqlite"

# Ollama model configuration
# NOTE: Changing EMBEDDINGS_MODEL invalidates the FAISS index.
#       Run `bgrules faiss-clear` before using the new model.
EMBEDDINGS_MODEL = "llama3"
LLM_MODEL = "llama3"

OLLAMA_BASE_URL = "http://localhost:11434"

# BoardGameGeek XML API token. Create an approved application and token at:
# https://boardgamegeek.com/applications
BGG_API_TOKEN = os.environ.get("BGG_API_TOKEN", "").strip()
