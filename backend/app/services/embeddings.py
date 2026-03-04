from typing import List
from config import embeddings


def embed_text(text: str) -> List[float]:
    """Generate an embedding vector using the shared OpenAI embeddings instance."""
    try:
        return embeddings.embed_query(text)
    except Exception:
        return []