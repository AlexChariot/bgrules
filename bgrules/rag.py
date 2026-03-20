import os
from pathlib import Path

from bgrules.scraper import CACHE_DIR
from bgrules.agents import ParserAgent

def _load_embeddings():
    # Support both langchain_ollama and newer langchain embeddings module variants
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
        raise RuntimeError("langchain_ollama ou langchain_community OllamaEmbeddings est requis. Installez langchain-ollama ou langchain-community.") from e

def _load_llm():
    # support both modules depending on langchain version
    try:
        from langchain_ollama import Ollama
        return Ollama(model="llama3")
    except ImportError:
        pass

    try:
        from langchain_community.llms import Ollama
        return Ollama(model="llama3")
    except ImportError:
        pass

    try:
        from langchain.llms import Ollama
        return Ollama(model="llama3")
    except ImportError as e:
        raise RuntimeError("langchain_ollama ou langchain_community Ollama est requis. Installez langchain-ollama ou langchain-community.") from e

def _load_cached_texts():
    """Load text from all cached PDFs."""
    import json

    path = Path(CACHE_DIR)
    parser = ParserAgent()

    # Load cache index to resolve MD5 hashes → game names
    index_path = path / ".cache_index.json"
    cache_index = {}
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                cache_index = json.load(f)
        except Exception:
            pass

    pdf_files = list(path.glob("*.pdf"))
    # Sort by resolved game name (alphabetical) rather than by MD5 hash filename
    pdf_files.sort(key=lambda p: cache_index.get(p.stem, p.name).lower())
    total_files = len(pdf_files)
    print(f"📂 Indexation de {total_files} fichiers PDF en cache...")

    for i, pdf_file in enumerate(pdf_files, start=1):
        game_name = cache_index.get(pdf_file.stem, pdf_file.name)
        print(f"📄 Traitement du fichier PDF {i}/{total_files}: {game_name}")
        try:
            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()
            text = parser.run(pdf_bytes)
            if text:
                yield f"{pdf_file.stem}\n{text}"
        except Exception as e:
            print(f"❌ Erreur lors du traitement du fichier PDF {pdf_file.name}: {e}")
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
    """Persist the set of indexed PDF stems."""
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

    # Determine which PDF(s) to consider
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
            raise RuntimeError("langchain_community FAISS vectorstore est requis: installez langchain-community et faiss-cpu.") from e

    # Load existing index if available
    faiss_index = None
    indexed_stems = _get_indexed_stems()
    if os.path.exists(FAISS_INDEX_DIR) and indexed_stems:
        try:
            faiss_index = FAISS.load_local(FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
            print(f"✓ Index FAISS chargé ({len(indexed_stems)} document(s) déjà indexé(s)).")
        except Exception as e:
            print(f"⚠️  Impossible de charger l'index existant, reconstruction : {e}")
            faiss_index = None
            indexed_stems = set()

    # Find PDFs not yet indexed
    parser = ParserAgent()
    new_files = [p for p in pdf_files if p.stem not in indexed_stems]

    if not new_files:
        print("✓ Tous les documents sont déjà indexés.")
    else:
        print(f"🧮 Génération des embeddings pour {len(new_files)} nouveau(x) document(s)...")
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
                print(f"\n❌ Erreur lors de l'indexation de {game_name}: {e}")
                continue

        print()  # newline after \r
        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
        faiss_index.save_local(FAISS_INDEX_DIR)
        _save_indexed_stems(indexed_stems)
        print("✓ Index FAISS sauvegardé.")

    if faiss_index is None:
        return None
    return faiss_index.as_retriever(search_kwargs={"k": 4})

def rag_answer(question: str, retriever):
    """Answer a question via retrieval chain."""
    if not retriever:
        raise RuntimeError("No retriever available. Assurez-vous que des PDFs sont en cache.")

    llm = _load_llm()
    try:
        from langchain.chains import RetrievalQA
    except ImportError:
        try:
            from langchain_community.chains import RetrievalQA
        except ImportError as e:
            raise RuntimeError("langchain RetrievalQA est requis. Installez langchain ou langchain-community.") from e

    chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
    )
    result = chain({
        "query": question
    })
    return result

def interactive_rag(game: str = None):
    """Run an interactive RAG chat session."""
    print("\n🔄 Indexation des PDFs en cache...")
    retriever = build_retriever(game=game)
    if retriever is None:
        raise RuntimeError("Aucun fichier PDF en cache pour construire l'index RAG. Exécutez d'abord `bgrules find <jeu>`.")

    print("✓ Index RAG prêt !\n")
    print("📚 Chat RAG actif. Posez des questions sur les règles (tapez 'exit' pour quitter).\n")
    
    while True:
        prompt = input("❓ Question > ").strip()
        if prompt.lower() in {"exit", "quit", "q"}:
            print("\n👋 Fin du chat RAG.")
            break
        
        if not prompt:
            continue

        try:
            print("\n🤔 Traitement de votre question...")
            answer = rag_answer(prompt, retriever)
            print("✓ Réponse :\n")
            print(answer)
            print("\n" + "="*80 + "\n")
        except Exception as exc:
            print(f"❌ Erreur lors de la réponse RAG : {exc}\n")