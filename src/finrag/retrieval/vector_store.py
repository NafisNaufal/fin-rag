import hashlib
from threading import RLock

from qdrant_client import QdrantClient, models

from finrag.models import Chunk, Source


class VectorStore:
    def __init__(self, path: str, model_name: str):
        self.client = QdrantClient(path=path)
        self.collection = "reports_" + hashlib.sha256(model_name.encode()).hexdigest()[:12]
        self.lock = RLock()

    def close(self):
        self.client.close()

    def add(self, chunks: list[Chunk], vectors: list[list[float]]):
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("Each chunk requires an embedding.")
        with self.lock:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    self.collection,
                    vectors_config=models.VectorParams(
                        size=len(vectors[0]), distance=models.Distance.COSINE
                    ),
                )
            for start in range(0, len(chunks), 64):
                self.client.upsert(
                    self.collection,
                    points=[
                        models.PointStruct(id=c.id, vector=v, payload=c.model_dump())
                        for c, v in zip(
                            chunks[start : start + 64], vectors[start : start + 64], strict=True
                        )
                    ],
                    wait=True,
                )

    def search(self, vector: list[float], top_k: int, document_ids: list[str]) -> list[Source]:
        with self.lock:
            if not document_ids or not self.client.collection_exists(self.collection):
                return []
            condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchAny(any=document_ids)
                    )
                ]
            )
            result = self.client.query_points(
                self.collection,
                query=vector,
                limit=top_k,
                query_filter=condition,
                with_payload=True,
            )
            return [
                Source(label=f"S{i}", chunk=Chunk.model_validate(point.payload), score=point.score)
                for i, point in enumerate(result.points, 1)
            ]

    def delete(self, document_id: str):
        with self.lock:
            if self.client.collection_exists(self.collection):
                self.client.delete(
                    self.collection,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="document_id", match=models.MatchValue(value=document_id)
                                )
                            ]
                        )
                    ),
                    wait=True,
                )
