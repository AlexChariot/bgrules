import requests
from ddgs import DDGS
import os
import hashlib
import unicodedata
from bgrules.config import is_debug_mode


def debug_print(message):
    """Print debug message only if DEBUG_MODE is enabled."""
    if is_debug_mode():
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


def _ascii_fallback(text):
    """Return an ASCII-only variant of *text* for search fallback."""
    normalized = unicodedata.normalize("NFKD", text)
    fallback = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(fallback.split())


def _build_search_queries(game):
    """Build ordered search query variants for resilient DDGS lookup."""
    queries = [
        f'"{game}" rules filetype:pdf',
        f'"{game}" rulebook filetype:pdf',
        f'"{game}" manuel filetype:pdf',
        f'"{game}" regles filetype:pdf',
        f'{game} rules filetype:pdf',
    ]

    ascii_game = _ascii_fallback(game)
    if ascii_game and ascii_game.lower() != game.lower():
        queries.extend(
            [
                f'"{ascii_game}" rules filetype:pdf',
                f'"{ascii_game}" rulebook filetype:pdf',
                f'"{ascii_game}" manuel filetype:pdf',
                f'"{ascii_game}" regles filetype:pdf',
                f"{ascii_game} rules filetype:pdf",
            ]
        )

    deduped_queries = []
    seen_queries = set()
    for query in queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        deduped_queries.append(query)

    return deduped_queries


def _ddgs_text_results(query, max_results=10):
    """Search DDGS with stable backend fallbacks instead of aborting on one engine."""
    backends = [
        "google",
        "duckduckgo",
        "yahoo",
        "mojeek",
    ]

    last_error = None
    with DDGS() as ddgs:
        for backend in backends:
            try:
                debug_print(f"DEBUG: DDGS search using backend={backend!r}, query={query!r}")
                return ddgs.text(query, max_results=max_results, backend=backend)
            except Exception as e:
                last_error = e
                debug_print(f"DEBUG: DDGS backend {backend!r} failed: {e}")

    if last_error:
        debug_print(f"DEBUG: All DDGS backends failed for query={query!r}: {last_error}")
    return []


def search(game):
    """Search for PDF rules, preferring exact matches."""
    results = []
    seen_urls = set()

    for query in _build_search_queries(game):
        query_results = _ddgs_text_results(query, max_results=10)
        for result in query_results:
            href = result.get("href")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            results.append(href)

    debug_print(f"DEBUG: Found {len(results)} results for search: {game}")

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


def download_pdf_from_url(url, timeout=20):
    """Download a PDF from a direct URL.

    Accepts standard application/pdf responses and also tolerates URLs ending
    with .pdf when servers send an incorrect content-type.
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "bgrules/1.0"},
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        final_url = response.url.lower()
        looks_like_pdf = (
            "pdf" in content_type
            or final_url.endswith(".pdf")
            or url.lower().endswith(".pdf")
        )

        if not looks_like_pdf:
            debug_print(
                f"DEBUG: URL did not look like a PDF (content-type={content_type!r}, final_url={response.url!r})"
            )
            return None

        pdf_bytes = response.content
        if not pdf_bytes:
            debug_print("DEBUG: Empty response body while downloading PDF")
            return None

        # Lightweight structural check: PyMuPDF must be able to open it.
        try:
            import fitz

            fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            debug_print(f"DEBUG: Downloaded content is not a valid PDF: {e}")
            return None

        return pdf_bytes
    except requests.exceptions.RequestException as e:
        debug_print(f"DEBUG: PDF download failed for {url}: {e}")
        return None


def safe_download(url):
    return download_pdf_from_url(url, timeout=10)


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
    """Save PDF bytes to cache and update index."""
    if pdf_bytes:
        cache_path = get_cache_path(game)
        with open(cache_path, "wb") as f:
            f.write(pdf_bytes)
        debug_print(f"DEBUG: Saved {game} rules to cache: {cache_path}")
        
        # Update cache index
        _update_cache_index(game, cache_path)
        return cache_path
    return None


def remove_from_cache(game):
    """Remove a cached PDF and its cache-index entry for *game*."""
    import json

    cache_path = get_cache_path(game)
    removed_pdf = False
    if os.path.exists(cache_path):
        os.unlink(cache_path)
        removed_pdf = True
        debug_print(f"DEBUG: Removed cached PDF for {game}: {cache_path}")

    index_path = _get_cache_index_path()
    removed_index = False
    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                index = json.load(f)
        except Exception as e:
            debug_print(f"DEBUG: Could not read cache index while removing {game}: {e}")
            index = {}

        safe_name = hashlib.md5(game.lower().encode()).hexdigest()
        if safe_name in index:
            del index[safe_name]
            with open(index_path, "w") as f:
                json.dump(index, f, indent=2)
            removed_index = True
            debug_print(f"DEBUG: Removed cache index entry for {game}")

    return removed_pdf or removed_index


def _get_cache_index_path():
    """Get path to the cache index file."""
    return os.path.join(CACHE_DIR, ".cache_index.json")


def _update_cache_index(game, pdf_path):
    """Update the cache index mapping game names to PDF paths."""
    import json
    
    index_path = _get_cache_index_path()
    
    # Read existing index
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            index = json.load(f)
    else:
        index = {}
    
    # Update with new entry
    safe_name = hashlib.md5(game.lower().encode()).hexdigest()
    index[safe_name] = game
    
    # Write back
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    
    debug_print(f"DEBUG: Updated cache index with {game}")


def rebuild_cache_index():
    """Rebuild cache index based on existing PDF files in the cache folder."""
    import json
    from pathlib import Path

    index_path = _get_cache_index_path()
    cache_path = Path(CACHE_DIR)

    existing_index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                existing_index = json.load(f)
        except Exception as e:
            debug_print(f"DEBUG: Could not read existing cache index: {e}")
            existing_index = {}

    pdf_files = sorted(cache_path.glob("*.pdf"))

    rebuilt_index = {}
    for pdf_file in pdf_files:
        key = pdf_file.stem
        if key in existing_index:
            rebuilt_index[key] = existing_index[key]
        else:
            # We don't have a mapped game name, keep a placeholder.
            rebuilt_index[key] = f"<cached:{key}>"

    try:
        with open(index_path, "w") as f:
            json.dump(rebuilt_index, f, indent=2)
        debug_print(f"DEBUG: Rebuilt cache index with {len(rebuilt_index)} entries")
    except Exception as e:
        debug_print(f"DEBUG: Failed to write rebuilt cache index: {e}")

    return rebuilt_index



def get_cached_games():
    """Get list of all cached games sorted alphabetically."""
    import json
    from pathlib import Path

    index_path = _get_cache_index_path()

    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                index = json.load(f)
            games = sorted(index.values())
            if games:
                return games
        except Exception as e:
            debug_print(f"DEBUG: Could not read cache index: {e}")

    # Rebuild index from existing PDF files if index was missing/empty
    rebuilt_index = rebuild_cache_index()
    return sorted(rebuilt_index.values())



def load_from_cache(game):
    """Load PDF bytes from cache."""
    cache_path = get_cache_path(game)
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
        debug_print(f"DEBUG: Loaded {game} rules from cache: {cache_path}")
        return data
    return None
