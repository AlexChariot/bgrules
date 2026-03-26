import os
from pathlib import Path

from bgrules.scraper import CACHE_DIR
from bgrules.agents import ParserAgent


def _load_embeddings():
    from bgrules.ollama import ensure_required_models_available, get_current_embeddings_model

    ensure_required_models_available()
    model = get_current_embeddings_model()

    try:
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(model=model)
    except ImportError:
        pass
    try:
        from langchain_community.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(model=model)
    except ImportError:
        pass
    try:
        from langchain.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(model=model)
    except ImportError as e:
        raise RuntimeError(
            "OllamaEmbeddings is required. Install with: pip install -U langchain-ollama"
        ) from e


def _load_llm():
    from bgrules.ollama import ensure_required_models_available, get_current_llm_model

    ensure_required_models_available()
    model = get_current_llm_model()

    try:
        from langchain_ollama import OllamaLLM
        return OllamaLLM(model=model)
    except ImportError:
        pass
    try:
        from langchain_community.llms import Ollama
        return Ollama(model=model)
    except ImportError as e:
        raise RuntimeError(
            "langchain-ollama is required. Install with: pip install -U langchain-ollama"
        ) from e


# Root directory that contains one sub-folder per game (named after the MD5 stem).
FAISS_INDEX_DIR = os.path.join(os.path.dirname(__file__), "faiss_index")


def _game_index_dir(stem: str) -> str:
    """Return the FAISS index directory for a specific game stem."""
    return os.path.join(FAISS_INDEX_DIR, stem)


def _load_faiss():
    try:
        from langchain_community.vectorstores import FAISS
        return FAISS
    except ImportError:
        pass
    try:
        from langchain.vectorstores import FAISS
        return FAISS
    except ImportError as e:
        raise RuntimeError(
            "FAISS vectorstore is required. "
            "Install with: pip install langchain-community faiss-cpu"
        ) from e


def _build_game_index(stem: str, pdf_path: Path, game_name: str, embeddings) -> object:
    """Build (or load if already up to date) the FAISS index for a single game.

    Returns the FAISS index object, or None on failure.
    """
    FAISS = _load_faiss()
    index_dir = _game_index_dir(stem)

    # If an index already exists for this game, load and return it directly.
    if os.path.exists(index_dir):
        try:
            index = FAISS.load_local(
                index_dir, embeddings, allow_dangerous_deserialization=True
            )
            print(f"  ✓ {game_name}: index loaded from cache.")
            return index
        except Exception as e:
            print(f"  ⚠️  {game_name}: could not load existing index, rebuilding ({e})")

    # Build a fresh index for this game.
    parser = ParserAgent()
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        text = parser.run(pdf_bytes)
        if not text:
            print(f"  ✗ {game_name}: no text extracted, skipping.")
            return None

        index = FAISS.from_texts([text], embeddings)
        os.makedirs(index_dir, exist_ok=True)
        index.save_local(index_dir)
        print(f"  ✓ {game_name}: index built and saved.")
        return index
    except Exception as e:
        print(f"  ✗ {game_name}: error during indexing ({e})")
        return None


def build_retriever(game: str = None):
    """Build a FAISS retriever scoped to a single game, or all cached games.

    When *game* is provided, only that game's isolated index is used —
    guaranteeing that answers never bleed across games.
    When *game* is None, a merged in-memory index across all cached games is
    built (useful for cross-game queries, though isolation is lost).
    """
    import json
    import hashlib

    path = Path(CACHE_DIR)
    embeddings = _load_embeddings()
    FAISS = _load_faiss()

    # Resolve cache index (stem -> game name)
    cache_index: dict[str, str] = {}
    index_path = path / ".cache_index.json"
    if index_path.exists():
        try:
            with open(index_path) as f:
                cache_index = json.load(f)
        except Exception:
            pass

    if game:
        # --- Single-game mode: strict isolation ---
        stem = hashlib.md5(game.lower().encode()).hexdigest()
        pdf_files = [p for p in path.glob("*.pdf") if p.stem == stem]
        if not pdf_files:
            return None

        pdf_path = pdf_files[0]
        game_name = cache_index.get(stem, game)
        print(f"🔄 Loading index for '{game_name}'...")
        index = _build_game_index(stem, pdf_path, game_name, embeddings)
        if index is None:
            return None
        return index.as_retriever(search_kwargs={"k": 4})

    else:
        # --- All-games mode: merge individual indexes in memory ---
        pdf_files = sorted(
            path.glob("*.pdf"),
            key=lambda p: cache_index.get(p.stem, p.name).lower(),
        )
        if not pdf_files:
            return None

        print(f"🔄 Loading indexes for {len(pdf_files)} game(s)...")
        merged: object = None
        for pdf_path in pdf_files:
            stem = pdf_path.stem
            game_name = cache_index.get(stem, pdf_path.name)
            index = _build_game_index(stem, pdf_path, game_name, embeddings)
            if index is None:
                continue
            if merged is None:
                merged = index
            else:
                merged.merge_from(index)

        if merged is None:
            return None
        return merged.as_retriever(search_kwargs={"k": 4})


def rag_answer(question: str, retriever):
    """Answer a question via a LCEL retrieval chain (langchain >= 0.2)."""
    if not retriever:
        raise RuntimeError("No retriever available. Make sure PDFs are cached first.")

    llm = _load_llm()

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.runnables import RunnablePassthrough
    except ImportError as e:
        raise RuntimeError(
            "langchain-core is required. Install with: pip install langchain-core"
        ) from e

    prompt = ChatPromptTemplate.from_template(
        """You are an assistant specialized in board game rules.
Answer the question based solely on the provided context.
If the answer cannot be found in the context, say so clearly.

Context:
{context}

Question: {question}

Answer:"""
    )

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    answer_text = chain.invoke(question)
    source_docs = retriever.invoke(question)

    return {
        "result": answer_text,
        "source_documents": source_docs,
    }


def _open_pdf(game: str) -> None:
    """Open the cached PDF for *game* with the system's default viewer."""
    import subprocess
    import shutil
    import sys as _sys
    from bgrules.scraper import get_cache_path

    pdf_path = get_cache_path(game)
    if not os.path.exists(pdf_path):
        print(f"  ✗ No cached PDF found for '{game}'.")
        return

    if _sys.platform == "darwin":
        subprocess.Popen(["open", pdf_path])
        print(f"  📄 Opening PDF for '{game}'...")
        return
    elif _sys.platform == "win32":
        os.startfile(pdf_path)
        print(f"  📄 Opening PDF for '{game}'...")
        return

    # Linux: try known PDF viewers in order of preference
    PDF_VIEWERS = ["evince", "okular", "zathura", "mupdf", "atril", "xdg-open"]
    viewer = next((v for v in PDF_VIEWERS if shutil.which(v)), None)

    if viewer:
        subprocess.Popen([viewer, pdf_path],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        print(f"  📄 Opening PDF for '{game}' with {viewer}...")
    else:
        print(f"  ✗ No PDF viewer found. Install one: apt install evince")
        print(f"  ℹ️  PDF path: {pdf_path}")


def interactive_rag(game: str = None):
    """Run an interactive RAG chat session."""
    print()
    retriever = build_retriever(game=game)
    if retriever is None:
        raise RuntimeError(
            "No cached PDF found to build the RAG index. "
            "Run `bgrules find <game>` first."
        )

    scope = f"'{game}'" if game else "all cached games"
    print(f"✓ RAG index ready ({scope})!\n")

    help_line = "(type 'pdf' to open the rulebook, 'exit' to quit)"
    if not game:
        help_line = "(type 'exit' to quit)"
    print(f"📚 RAG chat active. Ask questions about the rules {help_line}.\n")

    while True:
        user_prompt = input("❓ Question > ").strip()

        if user_prompt.lower() in {"exit", "quit", "q"}:
            print("\n👋 RAG chat session ended.")
            break

        if not user_prompt:
            continue

        if user_prompt.lower() == "pdf":
            if game:
                _open_pdf(game)
            else:
                print("  ℹ️  'pdf' is only available when a single game is selected (--game).")
            continue

        try:
            print("\n🤔 Processing your question...")
            answer = rag_answer(user_prompt, retriever)
            print("✓ Answer:\n")
            print(answer["result"])
            print("\n" + "=" * 80 + "\n")
        except Exception as exc:
            print(f"❌ RAG error: {exc}\n")

def clear_game_index(game: str) -> bool:
    """Delete the cached FAISS index for a specific game, if it exists."""
    import hashlib
    import shutil

    stem = hashlib.md5(game.lower().encode()).hexdigest()
    index_dir = _game_index_dir(stem)

    if os.path.exists(index_dir):
        shutil.rmtree(index_dir)
        return True
    return False
