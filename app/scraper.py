import requests
from ddgs import DDGS
import os
import hashlib
from config import DEBUG_MODE


def debug_print(message):
    """Print debug message only if DEBUG_MODE is enabled."""
    if DEBUG_MODE:
        print(message)


# Cache directory for storing downloaded PDFs
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_path(game):
    """Generate cache filename from game name."""
    safe_name = hashlib.md5(game.lower().encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe_name}.pdf")


def cache_exists(game):
    """Check if rules for this game are already cached."""
    return os.path.exists(get_cache_path(game))


def detect_language(text):
    """Detect language of text. Returns 'fr', 'en', or other language code."""
    try:
        from langdetect import detect
        lang = detect(text)
        return lang
    except Exception as e:
        debug_print(f"DEBUG: Language detection failed: {e}")
        return None


def _is_game_name_in_url(game, url):
    """Check if game name appears as a distinct word in the URL (not as substring)."""
    import re
    url_lower = url.lower()
    game_lower = game.lower()
    
    # Split URL into words (separated by /, -, _, ., ?)
    words = re.split(r'[\-_/.\?]', url_lower)
    
    # Check for exact word match or substring at start of word
    for word in words:
        if word == game_lower or word.startswith(game_lower):
            return True
    return False


def _validate_pdf_content(pdf_bytes, game):
    """Check if PDF actually contains the game name (rough validation)."""
    try:
        text = extract_text_from_pdf(pdf_bytes)
        if not text:
            return False
        
        # Check if game name appears in extracted text (case insensitive)
        text_lower = text.lower()
        game_lower = game.lower()
        
        # Count occurrences of game name
        occurrences = text_lower.count(game_lower)
        debug_print(f"DEBUG: Found '{game}' {occurrences} times in PDF")
        
        # If game name appears at least twice, it's likely the right PDF
        return occurrences >= 2
    except Exception as e:
        debug_print(f"DEBUG: Could not validate PDF content: {e}")
        return False


def search(game):
    """Search for PDF rules, preferring exact matches."""
    with DDGS() as ddgs:
        # First try with exact match (quoted)
        results = [r["href"] for r in ddgs.text(f'"{game}" rules filetype:pdf', max_results=10)]
        debug_print(f"DEBUG: Found {len(results)} results for exact search: {game}")
        
        # Filter to strongly prefer results that contain the exact game name as distinct word
        strong_matches = []
        weak_matches = []
        
        for url in results:
            if _is_game_name_in_url(game, url):
                strong_matches.append(url)
            else:
                weak_matches.append(url)
        
        debug_print(f"DEBUG: {len(strong_matches)} strong matches, {len(weak_matches)} weak matches")
        
        # Return strong matches first, then weak if needed
        return strong_matches + weak_matches


def safe_download(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and "pdf" in r.headers.get("content-type", ""):
            return r.content
    except requests.exceptions.RequestException:
        return None


def extract_text_from_pdf(pdf_bytes):
    """Extract text from PDF bytes for language detection."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join([p.get_text() for p in doc[:3]])  # First 3 pages only
        return text[:1000]  # First 1000 chars
    except Exception as e:
        debug_print(f"DEBUG: PDF text extraction failed: {e}")
        return None


def save_to_cache(game, pdf_bytes):
    """Save PDF bytes to cache."""
    if pdf_bytes:
        cache_path = get_cache_path(game)
        with open(cache_path, "wb") as f:
            f.write(pdf_bytes)
        debug_print(f"DEBUG: Saved {game} rules to cache: {cache_path}")
        return cache_path
    return None


def load_from_cache(game):
    """Load PDF bytes from cache."""
    cache_path = get_cache_path(game)
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
        debug_print(f"DEBUG: Loaded {game} rules from cache: {cache_path}")
        return data
    return None