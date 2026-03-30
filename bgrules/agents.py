from bgrules.config import is_debug_mode


def _debug_print(message):
    """Print debug message only if DEBUG_MODE is enabled."""
    if is_debug_mode():
        print(message)


class SearchAgent:
    def run(self, game):
        _debug_print(f"DEBUG: SearchAgent running with game={game!r}")
        from bgrules.scraper import search, cache_exists

        if cache_exists(game):
            _debug_print(f"DEBUG: Found {game} in cache, skipping search")
            return None

        return search(game)


class FilterAgent:
    def run(self, urls):
        _debug_print(f"DEBUG: FilterAgent running with urls={urls!r}")
        from urllib.parse import urlparse

        from bgrules.config import ALLOWED_DOMAINS

        # Keep candidates that come from configured/trusted rulebook sources and
        # deduplicate them while preserving order.
        filtered = []
        seen = set()
        for url in urls:
            if not url or url in seen:
                continue
            hostname = urlparse(url).netloc.lower()
            if ALLOWED_DOMAINS and not any(domain in hostname for domain in ALLOWED_DOMAINS):
                _debug_print(f"DEBUG: Skipping untrusted domain for url={url!r}")
                continue
            seen.add(url)
            filtered.append(url)
        _debug_print(f"DEBUG: FilterAgent output={filtered!r}")
        return filtered


class DownloadAgent:
    def __init__(self, game=None):
        self.game = game

    def run(self, urls, game=None):
        _debug_print(f"DEBUG: DownloadAgent running with urls={urls!r}")
        from bgrules.scraper import (
            safe_download,
            load_from_cache,
            detect_language,
            extract_text_from_pdf,
            _validate_pdf_content,
        )

        target_game = game or self.game

        # Check if we should load from cache
        if not urls and target_game:
            cached_data = load_from_cache(target_game)
            if cached_data:
                return [(f"cache://{target_game}", cached_data)]

        # Download URLs, preferring cdn.1j1ju.com URLs first
        urls_sorted = sorted(urls, key=lambda url: 0 if "cdn.1j1ju.com" in url else 1)

        # Collect all valid candidates: French ones first, then English fallbacks
        french_candidates = []
        english_candidates = []

        for u in urls_sorted:
            _debug_print(f"DEBUG: Trying URL: {u}")
            content = safe_download(u)
            if not content:
                _debug_print(f"DEBUG: Failed to download {u}")
                continue

            # Validate that PDF actually contains the game name
            valid_content = _validate_pdf_content(content, target_game)
            if not valid_content and "cdn.1j1ju.com" not in u:
                _debug_print(f"DEBUG: PDF doesn't contain game '{target_game}', skipping")
                continue
            if not valid_content and "cdn.1j1ju.com" in u:
                _debug_print(f"DEBUG: Accepting cdn.1j1ju.com PDF even if content validation is weak")

            # Extract text and detect language
            text = extract_text_from_pdf(content)
            if not text:
                _debug_print(f"DEBUG: Could not extract text from {u}")
                continue

            lang = detect_language(text)
            _debug_print(f"DEBUG: Detected language: {lang} for {u}")

            if lang == "fr":
                french_candidates.append((u, content))
            else:
                english_candidates.append((u, content))

        # Return French candidates first, then English ones
        candidates = french_candidates + english_candidates
        _debug_print(f"DEBUG: DownloadAgent found {len(candidates)} candidate(s)")
        return candidates


class ParserAgent:
    def run(self, pdf_bytes):
        _debug_print(f"DEBUG: ParserAgent running with bytes_length={len(pdf_bytes) if pdf_bytes is not None else 'None'}")
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parsed = "\n".join([p.get_text() for p in doc])
        _debug_print(f"DEBUG: ParserAgent output_length={len(parsed)}")
        return parsed
