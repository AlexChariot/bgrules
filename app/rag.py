from langchain.vectorstores import FAISS
from langchain.embeddings import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="llama3")


def build_index(texts):
    return FAISS.from_texts(texts, embeddings)