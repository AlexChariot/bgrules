import os
from pathlib import Path

from bgrules.scraper import CACHE_DIR
from bgrules.agents import ParserAgent


def _load_embeddings():
    # Prefer langchain_ollama; fall back to langchain_community, then langchain
    try:
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(model="llama3")
    except ImportError:
        pass

    try:
        from langchain_community.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(model="llama3")
    except ImportError:
        pass

    try:
        from langchain.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(model="llama3")
    except ImportError as e:
        raise RuntimeError(
            "OllamaEmbeddings is required. Install with: pip install -U langchain-ollama"
        ) from e


def _load_llm():
    # OllamaLLM is the current non-deprecated class (langchain-ollama >= 0.3.1)
    try:
        from langchain_ollama import OllamaLLM
        return OllamaLLM(model="llama3")
    except ImportError:
        pass

    # Legacy fallback: langchain_community (triggers deprecation warning)
    try:
        from langchain_community.llms import Ollama
        return Ollama(model="llama3")
    except ImportError as e:
        raise RuntimeError(
            "langchain-ollama is required. Install with: pip install -U langchain-ollama"
        ) from e


def _load_cached_texts():
    """Load text from all cached PDFs."""
    import json

    path = Path(CACHE_DIR)
    parser = ParserAgent()

    # Load cache index to resolve MD5 hashes -> game names
    index_path = path / ".cache_index.json"
    cache_index = {}
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                cache_index = json.load(f)
        except Exception:
            pass

    pdf_files = list(path.glob("*.pdf"))
    # Sort alphabetically by resolved game name rather than by raw MD5 filename
    pdf_files.sort(key=lambda p: cache_index.get(p.stem, p.name).lower())
    total_files = len(pdf_files)
    print(f"📂 Indexing {total_files} cached PDF file(s)...")

    for i, pdf_file in enumerate(pdf_files, start=1):
        game_name = cache_index.get(pdf_file.stem, pdf_file.name)
        print(f"📄 Processing PDF {i}/{total_files}: {game_name}")
        try:
            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()
            text = parser.run(pdf_bytes)
            if text:
                yield f"{pdf_file.stem}\n{text}"
        except Exception as e:
            print(f"❌ Error processing {pdf_file.name}: {e}")
            continue


FAISS_INDEX_DIR = os.path.join(os.path.dirname(__file__), "faiss_index")


def _get_indexed_stems() -> set:
    """Return the set of PDF stems already present in the persisted FAISS index."""
    import json
    meta_path = os.path.join(FAISS_INDEX_DIR, ".indexed_stems.json")
    if not os.path.exists(meta_path):
        return set()
    with open(meta_path) as f:
        return set(json.load(f))


def _save_indexed_stems(stems: set):
    """Persist the set of indexed PDF stems to disk."""
    import json
    os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
    meta_path = os.path.join(FAISS_INDEX_DIR, ".indexed_stems.json")
    with open(meta_path, "w") as f:
        json.dump(list(stems), f)


def build_retriever(game: str = None):
    """Build (or update) a FAISS retriever from cached PDFs.

    If a persisted index already exists, only PDFs not yet indexed are added.
    When *game* is provided, only that game's PDF is considered.
    """
    import json

    path = Path(CACHE_DIR)

    # Load cache index to resolve stems -> game names
    index_path = path / ".cache_index.json"
    cache_index = {}
    if index_path.exists():
        try:
            with open(index_path) as f:
                cache_index = json.load(f)
        except Exception:
            pass

    # Determine which PDF(s) to process
    if game:
        import hashlib
        stem = hashlib.md5(game.lower().encode()).hexdigest()
        pdf_files = [p for p in path.glob("*.pdf") if p.stem == stem]
    else:
        pdf_files = sorted(
            path.glob("*.pdf"),
            key=lambda p: cache_index.get(p.stem, p.name).lower(),
        )

    if not pdf_files:
        return None

    embeddings = _load_embeddings()
    try:
        from langchain_community.vectorstores import FAISS
    except ImportError:
        try:
            from langchain.vectorstores import FAISS
        except ImportError as e:
            raise RuntimeError(
                "FAISS vectorstore is required. "
                "Install with: pip install langchain-community faiss-cpu"
            ) from e

    # Load existing index if one is already persisted
    faiss_index = None
    indexed_stems = _get_indexed_stems()
    if os.path.exists(FAISS_INDEX_DIR) and indexed_stems:
        try:
            faiss_index = FAISS.load_local(
                FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True
            )
            print(f"✓ FAISS index loaded ({len(indexed_stems)} document(s) already indexed).")
        except Exception as e:
            print(f"⚠️  Could not load existing index, rebuilding: {e}")
            faiss_index = None
            indexed_stems = set()

    # Only process PDFs that are not yet in the index
    parser = ParserAgent()
    new_files = [p for p in pdf_files if p.stem not in indexed_stems]

    if not new_files:
        print("✓ All documents are already indexed.")
    else:
        print(f"🧮 Generating embeddings for {len(new_files)} new document(s)...")
        for i, pdf_file in enumerate(new_files, start=1):
            game_name = cache_index.get(pdf_file.stem, pdf_file.name)
            print(f"  [{i}/{len(new_files)}] {game_name}...", end="\r")
            try:
                with open(pdf_file, "rb") as f:
                    pdf_bytes = f.read()
                text = parser.run(pdf_bytes)
                if not text:
                    continue
                full_text = f"{pdf_file.stem}\n{text}"
                if faiss_index is None:
                    faiss_index = FAISS.from_texts([full_text], embeddings)
                else:
                    faiss_index.add_texts([full_text])
                indexed_stems.add(pdf_file.stem)
            except Exception as e:
                print(f"\n❌ Error indexing {game_name}: {e}")
                continue

        print()  # newline after \r
        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
        faiss_index.save_local(FAISS_INDEX_DIR)
        _save_indexed_stems(indexed_stems)
        print("✓ FAISS index saved.")

    if faiss_index is None:
        return None
    return faiss_index.as_retriever(search_kwargs={"k": 4})


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

    # Fetch source documents separately to keep the return value compatible
    # with callers expecting {"result": ..., "source_documents": [...]}
    source_docs = retriever.invoke(question)

    return {
        "result": answer_text,
        "source_documents": source_docs,
    }


def interactive_rag(game: str = None):
    """Run an interactive RAG chat session."""
    print("\n🔄 Indexing cached PDFs...")
    retriever = build_retriever(game=game)
    if retriever is None:
        raise RuntimeError(
            "No cached PDF found to build the RAG index. "
            "Run `bgrules find <game>` first."
        )

    print("✓ RAG index ready!\n")
    print("📚 RAG chat active. Ask questions about the rules (type 'exit' to quit).\n")

    while True:
        prompt = input("❓ Question > ").strip()
        if prompt.lower() in {"exit", "quit", "q"}:
            print("\n👋 RAG chat session ended.")
            break

        if not prompt:
            continue

        try:
            print("\n🤔 Processing your question...")
            answer = rag_answer(prompt, retriever)
            print("✓ Answer:\n")
            print(answer["result"])
            print("\n" + "=" * 80 + "\n")
        except Exception as exc:
            print(f"❌ RAG error: {exc}\n")