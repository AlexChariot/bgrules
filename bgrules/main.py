import sys
from pathlib import Path
import typer
from typing import Optional

from bgrules.agents import SearchAgent, FilterAgent, DownloadAgent, ParserAgent

# Main Typer app
app = typer.Typer(help="Board game rules retriever CLI", add_completion=False)


@app.command()
def find(
    game: str = typer.Argument(..., help="Name of the game to search rules for"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output"),
):
    """
    Search, download, and extract board game rules PDF.
    
    Example:
        bgrules find "Scythe"
        bgrules find "Catan" --debug
    """
    # Set debug mode in config
    if debug:
        sys.argv.append("--debug")
    
    # Import after setting debug mode to pick it up
    from bgrules.config import DEBUG_MODE
    
    if DEBUG_MODE:
        typer.echo(f"DEBUG: Running with game={game!r}, debug={debug}")
    
    s = SearchAgent()
    f = FilterAgent()
    d = DownloadAgent(game=game)
    p = ParserAgent()

    urls = s.run(game)
    urls = f.run(urls)
    downloads = d.run(urls, game=game)

    texts = []
    for url, content in downloads:
        if content:
            texts.append(p.run(content))

    typer.echo(f"✓ Processed {len(texts)} document(s)")


@app.command()
def list():
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
def cache_clear():
    """Clear all cached game rules."""
    from pathlib import Path
    cache_dir = Path(__file__).parent / "cache"
    
    if not cache_dir.exists():
        typer.echo("No cache directory found")
        return
    
    pdfs = list(cache_dir.glob("*.pdf"))
    for pdf in pdfs:
        pdf.unlink()
        typer.echo(f"Deleted {pdf.name}")

    # Also clear index file to keep listing state consistent
    index_file = cache_dir / ".cache_index.json"
    if index_file.exists():
        index_file.unlink()
        typer.echo("Deleted cache index file")

    if pdfs:
        typer.echo(f"✓ Cleared {len(pdfs)} cached file(s)")
    else:
        typer.echo("Cache was already empty")


@app.command()
def cache_rebuild():
    """Rebuild the cache index from existing cached PDFs."""
    from bgrules.scraper import rebuild_cache_index

    rebuilt = rebuild_cache_index()
    typer.echo(f"✓ Rebuilt cache index with {len(rebuilt)} entries")


@app.command()
def rag(
    game: Optional[str] = typer.Option(
        None,
        "--game",
        "-g",
        help="Nom du jeu à charger en cache avant le chat RAG (facultatif)",
    )
):
    """Open a RAG chat session against cached game rules."""
    from bgrules.rag import interactive_rag

    if game:
        # Assure que le jeu demandé est présent en cache avant démarrage RAG
        s = SearchAgent()
        f = FilterAgent()
        d = DownloadAgent(game=game)

        urls = s.run(game)
        urls = f.run(urls)
        d.run(urls, game=game)

        typer.echo(f"✓ '{game}' est chargé en cache (si trouvé)")

    interactive_rag(game=game)


if __name__ == "__main__": 
    app()