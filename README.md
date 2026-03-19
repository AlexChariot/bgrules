# Board Game Rules PDF Retriever (Legal Only)

Local AI system to find and chat with board game rules.

## Project structure
```
boardgame-ai/
├── app/
│   ├── agents.py          # Agents logic (search, filter, download, parse)
│   ├── scraper.py         # Scraping helper + cache and lang detection
│   └── main.py            # Orchestration (pipeline + CLI)
├── api/
├── ui/
├── data/
├── langflow/
├── pyproject.toml
└── README.md
```

## Architecture Diagram
```mermaid
flowchart LR
    A[User input game] --> B[SearchAgent]
    B -->|urls list| C[FilterAgent .pdf only]
    C -->|filtered urls| D[DownloadAgent]
    D -->|pdf bytes| E[ParserAgent]
    E -->|text| F[Output: processed docs]

    D --> G[Cache check]
    G -->|hit| D

    D --> H[cdn.1j1ju.com preferred]
``` 

## Pipeline sequence
```mermaid
sequenceDiagram
    participant U as User
    participant S as SearchAgent
    participant F as FilterAgent
    participant D as DownloadAgent
    participant P as ParserAgent
    participant C as Cache

    U->>S: run(game)
    S-->>F: urls
    F-->>D: filtered_urls
    D->>C: cache_exists(game)
    alt in cache
        C-->>D: pdf_bytes
    else not cached
        D->>D: fetch first URL (cdn.1j1ju.com first)
        D->>C: save to cache
    end
    D-->>P: pdf_bytes
    P-->>U: extracted text
```

## Stack
- LangChain
- Ollama (local LLM)
- UV (package + env manager)
- DuckDuckGo Search
- PyMuPDF

## Features
- Searches for official/legal board game rule PDFs
- Filters results using LLM + domain whitelist
- Downloads PDFs
- Extracts text

## Requirements
- Python 3.10+
- Ollama installed (https://ollama.com)
- UV installed (https://github.com/astral-sh/uv)

## Setup
### 1. Install Ollama and run:
```
ollama run llama3
```

### 2. Install uv:
```
curl -Ls https://astral.sh/uv/install.sh | sh
```
### 3. Create env + install dependencies:
```
uv sync
```
### 4. Run:
```
python main.py
```