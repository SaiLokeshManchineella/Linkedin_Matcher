from typing import List, Dict, Any, Tuple, Optional
import hashlib
from uuid import UUID
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from qdrant_client.http import models
from config import settings


class QdrantService:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection = settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

    @staticmethod
    def _url_to_point_id(linkedin_url: str) -> str:
        """Deterministic UUID from linkedin_url so re-submissions update the same point."""
        return str(UUID(hashlib.md5(linkedin_url.encode()).hexdigest()))

    def upsert_user(self, vector: List[float], payload: Dict[str, Any]) -> str:
        """Store a user embedding with their profile data as payload."""
        if len(vector) != 768:
            raise ValueError("Embedding must be 768 dimensions.")
        point_id = self._url_to_point_id(payload.get("linkedin_url", ""))
        self.client.upsert(
            collection_name=self.collection,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return point_id

    def get_user_vector(self, linkedin_url: str) -> List[float]:
        """Retrieve the stored vector for a user by their linkedin_url.
        Returns the vector if found, empty list otherwise.
        """
        point_id = self._url_to_point_id(linkedin_url)
        try:
            points = self.client.retrieve(
                collection_name=self.collection,
                ids=[point_id],
                with_vectors=True,
            )
            if points and points[0].vector:
                return list(points[0].vector)
        except Exception:
            pass
        return []

    def get_user_data(self, linkedin_url: str) -> Optional[Dict[str, Any]]:
        """Retrieve the stored payload and vector for a user by their linkedin_url.
        Returns dict containing 'vector' and 'payload' if found, None otherwise.
        """
        try:
            records, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="linkedin_url",
                            match=models.MatchValue(value=linkedin_url)
                        )
                    ]
                ),
                limit=1,
                with_vectors=True,
                with_payload=True,
            )
            if records:
                return {
                    "vector": list(records[0].vector) if records[0].vector else [],
                    "payload": records[0].payload or {}
                }
        except Exception:
            pass
        return None

    def find_similar_users(
        self,
        vector: List[float],
        limit: int = 10,
        threshold: float = 0.75,
        exclude_url: str = "",
    ) -> List[Dict[str, Any]]:
        """Search for top similar users above the similarity threshold.
        Returns list of dicts with 'score' and all payload fields.
        """
        if not vector:
            return []

        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=limit + 5,  # fetch extra to filter self-matches
        )

        matches: List[Dict[str, Any]] = []
        for hit in results:
            score = float(hit.score or 0.0)
            if score < threshold:
                continue
            payload = hit.payload or {}
            # Skip the current user
            if exclude_url and payload.get("linkedin_url") == exclude_url:
                continue
            matches.append({
                "similarity": round(score, 4),
                **payload,
            })
            if len(matches) >= limit:
                break

        return matches
