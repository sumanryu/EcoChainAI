"""
Day 2, Phase 2-3 — Load insight cards into Qdrant.

Embeds each card's summary text with a local sentence-transformers model
and upserts into Qdrant with the full card as payload (so search results
carry structured fields, not just text).

Prereq: Qdrant running locally.
    docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant

Run:
    python -m src.rag.load_qdrant
"""

import json

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src import config

def get_client() -> QdrantClient:
    return QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)

def ensure_collection(client: QdrantClient) -> None:
    if client.collection_exists(config.QDRANT_COLLECTION):
        client.delete_collection(config.QDRANT_COLLECTION)  # fresh load each run for v1
    client.create_collection(
        collection_name=config.QDRANT_COLLECTION,
        vectors_config=VectorParams(size=config.EMBEDDING_DIM, distance=Distance.COSINE),
    )

def run() -> None:
    with open(config.INSIGHTS_JSON) as f:
        cards = json.load(f)

    print(f"Loading embedding model ({config.EMBEDDING_MODEL})...")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    client = get_client()
    ensure_collection(client)

    print(f"Embedding {len(cards):,} cards...")
    summaries = [c["summary"] for c in cards]
    vectors = model.encode(summaries, show_progress_bar=True, batch_size=64)

    points = [
        PointStruct(id=i, vector=vectors[i].tolist(), payload=cards[i])
        for i in range(len(cards))
    ]

    # batch upsert to avoid one huge request
    batch_size = 500
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=config.QDRANT_COLLECTION, points=points[i:i + batch_size])

    count = client.count(config.QDRANT_COLLECTION).count
    print(f"Qdrant collection '{config.QDRANT_COLLECTION}' now has {count:,} points")


if __name__ == "__main__":
    run()
