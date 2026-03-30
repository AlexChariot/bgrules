from fastapi import FastAPI, HTTPException

from bgrules.agents import FilterAgent, SearchAgent
from bgrules.scraper import cache_exists

app = FastAPI()


@app.get("/search")
def search(game: str):
    """Return candidate rulebook URLs for a given game."""
    cached = cache_exists(game)
    try:
        urls = SearchAgent().run(game)
        filtered_urls = FilterAgent().run(urls)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "ok",
        "game": game,
        "results": filtered_urls,
        "cached": cached,
    }
