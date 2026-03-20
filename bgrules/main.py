import sys
from pathlib import Path
import typer
from typing import Optional

from bgrules.agents import SearchAgent, FilterAgent, DownloadAgent, ParserAgent

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

app = typer.Typer(help="Board game rules retriever CLI", add_completion=False)

cache_app = typer.Typer(help="Manage the local PDF cache.", add_completion=False)
app.add_typer(cache_app, name="cache")

llm_app = typer.Typer(help="Manage Ollama LLM and embeddings models.", add_completion=False)
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

        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            preview = doc[0].get_text()[:600].strip()
            typer.echo("─" * 60)
            typer.echo(preview)
            typer.echo("─" * 60)
        except Exception:
            typer.echo("  (Could not generate preview)")

        confirm = typer.confirm("Is this the correct rules PDF?")
        if confirm:
            chosen_content = content
            save_to_cache(game, content)
            typer.echo(f"✓ '{game}' saved to cache.")
            break
        else:
            typer.echo("  Skipping to next candidate...\n")

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
def rag(
    game: Optional[str] = typer.Option(
        None, "--game", "-g",
        help="Game to query (must already be cached via `find`).",
    )
):
    """Open an interactive RAG chat session against cached game rules."""
    from bgrules.rag import interactive_rag
    from bgrules.scraper import cache_exists

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