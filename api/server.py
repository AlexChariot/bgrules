from fastapi import FastAPI
from app.main import run

app = FastAPI()

@app.get("/search")
def search(game: str):
    run(game)
    return {"status": "ok"}