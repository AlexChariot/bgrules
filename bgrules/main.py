import sys
from pathlib import Path
import typer
from typing import Optional

from bgrules.agents import SearchAgent, FilterAgent, DownloadAgent, ParserAgent

# Allow both --help and -h on every command and sub-command
_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

app = typer.Typer(help="Board game rules retriever CLI", add_completion=False, context_settings=_CONTEXT_SETTINGS)

cache_app = typer.Typer(help="Manage the local PDF cache.", add_completion=False, context_settings=_CONTEXT_SETTINGS)
app.add_typer(cache_app, name="cache")

llm_app = typer.Typer(help="Manage Ollama LLM and embeddings models.", add_completion=False, context_settings=_CONTEXT_SETTINGS)
app.add_typer(llm_app, name="llm")


# ---------------------------------------------------------------------------
# Main commands  (find · list · rag)
# ---------------------------------------------------------------------------
    
@app.command()
def find(
    game: str = typer.Argument(..., help="Name of the game to search rules for"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
):
    """Search, download, and cache board game rules PDF."""
    if debug:
        sys.argv.append("--debug")

    from bgrules.config import DEBUG_MODE
    from bgrules.scraper import save_to_cache
    from bgrules.rag import clear_game_index

    if DEBUG_MODE:
        typer.echo(f"DEBUG: Running with game={game!r}, debug={debug}")

    s = SearchAgent()
    f = FilterAgent()
    d = DownloadAgent(game=game)
    p = ParserAgent()

    urls = s.run(game)

    # Cache hit: load directly without validation loop
    if not urls:
        candidates = d.run([], game=game)
        if candidates:
            typer.echo(f"✓ Loaded '{game}' from cache.")
            typer.echo("✓ Processed 1 document(s)")
        else:
            typer.echo("✗ No cached rules found.")
        return

    urls = f.run(urls)
    if not urls:
        typer.echo("✗ No PDF URLs found.")
        return

    candidates = d.run(urls, game=game)
    if not candidates:
        typer.echo("✗ No valid PDF could be downloaded.")
        return

    typer.echo(f"  Found {len(candidates)} candidate(s).\n")

    chosen_content = None
    for i, (url, content) in enumerate(candidates):
        typer.echo(f"[{i + 1}/{len(candidates)}] {url}")

        temp_file_path = None
        try:
            import tempfile
            import os
            import shutil
            import subprocess

            # Create a temporary file to save the PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # Open the PDF with the best available viewer
            if sys.platform == "win32":
                os.startfile(temp_file_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", temp_file_path])
            else:
                PDF_VIEWERS = ["evince", "okular", "zathura", "mupdf", "atril", "xdg-open"]
                viewer = next((v for v in PDF_VIEWERS if shutil.which(v)), None)
                if viewer:
                    subprocess.Popen([viewer, temp_file_path],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                else:
                    typer.echo(f"  ℹ️  No PDF viewer found. Install one: apt install evince")
                    typer.echo(f"  ℹ️  PDF path: {temp_file_path}")

            confirm = typer.confirm("Is this the correct rules PDF?")
            if confirm:
                chosen_content = content
                save_to_cache(game, content)
                clear_game_index(game)
                typer.echo(f"✓ '{game}' saved to cache.")
                break
            else:
                typer.echo("  Skipping to next candidate...\n")
        except Exception as e:
            typer.echo(f"  (Could not display PDF: {str(e)})")
        finally:
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except FileNotFoundError:
                    pass

    if chosen_content is None:
        typer.echo("✗ No suitable PDF was validated. Nothing saved to cache.")
        return

    p.run(chosen_content)
    typer.echo("✓ Processed 1 document(s)")


@app.command(name="list")
def list_games():
    """List all cached game rules (alphabetically sorted)."""
    from bgrules.scraper import get_cached_games

    games = get_cached_games()

    if not games:
        typer.echo("No cached games found")
        return

    typer.echo(f"Cached games ({len(games)}):")
    for game in games:
        typer.echo(f"  • {game}")


@app.command()
def add(
    game: str = typer.Argument(..., help="Name of the game to add to the cache"),
    url: str = typer.Argument(..., help="Direct URL to the rules PDF"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
):
    """Download a rules PDF from a direct URL and add it to the cache."""
    if debug:
        sys.argv.append("--debug")

    from bgrules.config import DEBUG_MODE
    from bgrules.scraper import download_pdf_from_url, save_to_cache
    from bgrules.rag import clear_game_index

    if DEBUG_MODE:
        typer.echo(f"DEBUG: Running with game={game!r}, url={url!r}, debug={debug}")

    pdf_bytes = download_pdf_from_url(url)
    if not pdf_bytes:
        typer.echo("✗ Could not download a valid PDF from the provided URL.", err=True)
        raise typer.Exit(code=1)

    save_to_cache(game, pdf_bytes)
    clear_game_index(game)

    try:
        p = ParserAgent()
        p.run(pdf_bytes)
    except Exception as e:
        typer.echo(f"⚠️  PDF downloaded and cached, but pre-processing failed: {e}")
        typer.echo(f"✓ '{game}' saved to cache.")
        raise typer.Exit(code=0)

    typer.echo(f"✓ '{game}' saved to cache.")
    typer.echo("✓ Processed 1 document(s)")


@app.command()
def rag(
    game: Optional[str] = typer.Argument(
        None,
        help="Game to query (must already be cached via `find`). Omit to query all cached games.",
    )
):
    """Open an interactive RAG chat session against cached game rules."""
    from bgrules.rag import interactive_rag
    from bgrules.scraper import cache_exists
    from bgrules.ollama import ensure_required_models_available

    if game:
        if not cache_exists(game):
            typer.echo(
                f"✗ '{game}' is not in the cache.\n"
                f'  Run first: bgrules find "{game}"',
                err=True,
            )
            raise typer.Exit(code=1)
        typer.echo(f"✓ '{game}' found in cache.")

    try:
        ensure_required_models_available()
        interactive_rag(game=game)
    except RuntimeError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# cache sub-commands  (bgrules cache <cmd>)
# ---------------------------------------------------------------------------

@cache_app.command(name="clear")
def cache_clear():
    """Delete all cached PDFs and the cache index."""
    cache_dir = Path(__file__).parent / "cache"

    if not cache_dir.exists():
        typer.echo("No cache directory found.")
        return

    pdfs = list(cache_dir.glob("*.pdf"))
    for pdf in pdfs:
        pdf.unlink()
        typer.echo(f"  Deleted {pdf.name}")

    index_file = cache_dir / ".cache_index.json"
    if index_file.exists():
        index_file.unlink()
        typer.echo("  Deleted cache index.")

    typer.echo(f"✓ Cleared {len(pdfs)} cached file(s)." if pdfs else "Cache was already empty.")


@cache_app.command(name="rebuild")
def cache_rebuild():
    """Rebuild the cache index from existing cached PDFs."""
    from bgrules.scraper import rebuild_cache_index

    rebuilt = rebuild_cache_index()
    typer.echo(f"✓ Rebuilt cache index with {len(rebuilt)} entries.")


# ---------------------------------------------------------------------------
# llm sub-commands  (bgrules llm <cmd>)
# ---------------------------------------------------------------------------

@llm_app.command(name="status")
def llm_status():
    """Show current LLM / embeddings models and Ollama availability."""
    from bgrules.ollama import model_status

    status = model_status()
    typer.echo(f"  LLM model       : {status['llm_model']}")
    typer.echo(f"  Embeddings model: {status['embeddings_model']}")

    if status["ollama_reachable"]:
        typer.echo(f"  Available models: {', '.join(status['available_models'])}")
        if not status["llm_available"]:
            typer.echo(f"  ⚠️  '{status['llm_model']}' not available — run: ollama pull {status['llm_model']}", err=True)
        if not status["embeddings_available"]:
            typer.echo(f"  ⚠️  '{status['embeddings_model']}' (embeddings) not available — run: ollama pull {status['embeddings_model']}", err=True)
    else:
        typer.echo("  ⚠️  Could not reach Ollama (is it running on localhost:11434?)", err=True)


@llm_app.command(name="set")
def llm_set(
    model: str = typer.Argument(..., help="Model name (e.g. mistral, llama3:8b)"),
):
    """Set the LLM model for this session."""
    from bgrules.ollama import set_llm_model, get_available_models

    available = get_available_models()
    if available and model not in available:
        typer.echo(f"⚠️  '{model}' not found. Available: {', '.join(available)}", err=True)
        raise typer.Exit(code=1)

    set_llm_model(model)
    typer.echo(f"✓ LLM model set to '{model}' for this session.")
    typer.echo("  (To make it permanent, edit LLM_MODEL in config.py)")


@llm_app.command(name="faiss-clear")
def faiss_clear(
    game: Optional[str] = typer.Option(
        None, "--game", "-g",
        help="Clear the index for a specific game only (clears all if omitted).",
    )
):
    """Clear the FAISS embeddings index (required after changing EMBEDDINGS_MODEL)."""
    import shutil
    import hashlib
    from bgrules.rag import FAISS_INDEX_DIR

    root = Path(FAISS_INDEX_DIR)

    if game:
        stem = hashlib.md5(game.lower().encode()).hexdigest()
        index_dir = root / stem
        if not index_dir.exists():
            typer.echo(f"No FAISS index found for '{game}'.")
            return
        shutil.rmtree(index_dir)
        typer.echo(f"✓ FAISS index cleared for '{game}'.")
    else:
        if not root.exists():
            typer.echo("No FAISS index found.")
            return
        shutil.rmtree(root)
        typer.echo("✓ FAISS index cleared (all games).")


if __name__ == "__main__":
    app()
