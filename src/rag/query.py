"""
Day 2, Phase 4 — RAG query loop.

embed question -> search Qdrant (top-k) -> stuff results as context -> ask
Ollama (llama3) to answer grounded in that context.

Run interactively:
    python -m src.rag.query
Or import `answer(question)` elsewhere (agents will do this in Day 3).
"""

import ollama
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src import config

_model = None  # lazy-loaded singleton, embedding model is slow to init


def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def search(question: str, top_k: int = config.RAG_TOP_K) -> list[dict]:
    client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
    query_vector = get_embedder().encode(question).tolist()
    hits = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_vector,
        limit=top_k,
    ).points
    return [hit.payload for hit in hits]


def build_prompt(question: str, cards: list[dict]) -> str:
    context = "\n".join(f"- {c['summary']}" for c in cards)
    return f"""You are a retail demand planning assistant. Answer the question
using ONLY the insight cards below. If the cards don't contain enough
information to answer, say so — do not make up numbers.

Insight cards:
{context}

Question: {question}

Answer concisely, referencing specific items/stores where relevant."""


def answer(question: str, top_k: int = config.RAG_TOP_K) -> str:
    cards = search(question, top_k)
    if not cards:
        return "No relevant insight cards found for this question."
    prompt = build_prompt(question, cards)
    response = ollama.chat(
        model=config.OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"]


if __name__ == "__main__":
    print("RAG query loop. Type a question, or 'quit' to exit.")
    while True:
        q = input("\n> ").strip()
        if q.lower() in ("quit", "exit"):
            break
        print(answer(q))
