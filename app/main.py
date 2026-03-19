import sys
from agents import *

def run(game):
    s = SearchAgent()
    f = FilterAgent()
    d = DownloadAgent(game=game)  # Pass game to DownloadAgent
    p = ParserAgent()

    urls = s.run(game)
    urls = f.run(urls)
    downloads = d.run(urls, game=game)  # Pass game to DownloadAgent.run()

    texts = []
    for url, content in downloads:
        if content:
            texts.append(p.run(content))

    print(f"Processed {len(texts)} documents")

if __name__ == "__main__":
    # Remove --debug from sys.argv so it doesn't get passed to input()
    if "--debug" in sys.argv:
        sys.argv.remove("--debug")
    
    run(input("Game: "))