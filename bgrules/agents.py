from bgrules.config import DEBUG_MODE


def _debug_print(message):
    """Print debug message only if DEBUG_MODE is enabled."""
    if DEBUG_MODE:
        print(message)


class SearchAgent:
    def run(self, game):
        _debug_print(f"DEBUG: SearchAgent running with game={game!r}")
        from bgrules.scraper import search, cache_exists
        
        if cache_exists(game):
            _debug_print(f"DEBUG: Found {game} in cache, skipping search")
            return []  # Return empty list since we'll load from cache in DownloadAgent
        
        return search(game)

class FilterAgent:
    def run(self, urls):
        _debug_print(f"DEBUG: FilterAgent running with urls={urls!r}")
        filtered = [u for u in urls if u.endswith(".pdf")]
        _debug_print(f"DEBUG: FilterAgent output={filtered!r}")
        return filtered

class DownloadAgent:
    def __init__(self, game=None):
        self.game = game
    
    def run(self, urls, game=None):
        _debug_print(f"DEBUG: DownloadAgent running with urls={urls!r}")
        from bgrules.scraper import safe_download, save_to_cache, load_from_cache, detect_language, extract_text_from_pdf, _validate_pdf_content
        
        target_game = game or self.game
        
        # Check if we should load from cache
        if not urls and target_game:
            cached_data = load_from_cache(target_game)
            if cached_data:
                return [(f"cache://{target_game}", cached_data)]
        
        # Download URLs, preferring cdn.1j1ju.com URLs first
        urls_sorted = sorted(urls, key=lambda url: 0 if 'cdn.1j1ju.com' in url else 1)
        downloaded = []
        french_pdf = None
        english_pdf = None
        
        for u in urls_sorted:
            _debug_print(f"DEBUG: Trying URL: {u}")
            content = safe_download(u)
            if not content:
                _debug_print(f"DEBUG: Failed to download {u}")
                continue
            
            # Validate that PDF actually contains the game name
            valid_content = _validate_pdf_content(content, target_game)
            if not valid_content and 'cdn.1j1ju.com' not in u:
                _debug_print(f"DEBUG: PDF doesn't contain game '{target_game}', skipping")
                continue
            if not valid_content and 'cdn.1j1ju.com' in u:
                _debug_print(f"DEBUG: Accepting cdn.1j1ju.com PDF even if content validation is weak")
            
            # Extract text and detect language
            text = extract_text_from_pdf(content)
            if not text:
                _debug_print(f"DEBUG: Could not extract text from {u}")
                continue
            
            lang = detect_language(text)
            _debug_print(f"DEBUG: Detected language: {lang} for {u}")
            
            if lang == 'fr':
                _debug_print(f"DEBUG: Found French PDF, using it")
                french_pdf = (u, content)
                break  # Prefer French, stop searching
            elif lang == 'en' and not english_pdf:
                _debug_print(f"DEBUG: Found English PDF as fallback")
                english_pdf = (u, content)
        
        # Use French if found, otherwise English, otherwise None
        if french_pdf:
            downloaded = [french_pdf]
        elif english_pdf:
            downloaded = [english_pdf]
        
        if downloaded and target_game:
            save_to_cache(target_game, downloaded[0][1])
        
        _debug_print(f"DEBUG: DownloadAgent output={[u for u, _ in downloaded]!r}")
        return downloaded

class ParserAgent:
    def run(self, pdf_bytes):
        _debug_print(f"DEBUG: ParserAgent running with bytes_length={len(pdf_bytes) if pdf_bytes is not None else 'None'}")
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parsed = "\n".join([p.get_text() for p in doc])
        _debug_print(f"DEBUG: ParserAgent output_length={len(parsed)}")
        return parsed