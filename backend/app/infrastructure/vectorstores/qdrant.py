from __future__ import annotations

import hashlib
from typing import Any, Sequence

import httpx

from app.domain.repositories.vector_store import VectorRecord, VectorStore, VectorStoreUnavailable


class QdrantVectorStore(VectorStore):
    def __init__(self, endpoint: str, collection: str, *, api_key: str = "", client: httpx.AsyncClient | None = None):
        self._endpoint = endpoint.rstrip("/")
        self._collection = collection
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        return {"api-key": self._api_key} if self._api_key else {}

    async def ensure_collection(self, name: str, dimension: int) -> None:
        response = await self._client.put(
            f"{self._endpoint}/collections/{name}",
            headers=self._headers(),
            json={"vectors": {"size": dimension, "distance": "Cosine"}},
        )
        if response.status_code not in {200, 201, 409}:
            raise VectorStoreUnavailable(f"Qdrant collection setup failed: HTTP {response.status_code}")

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        points = []
        for record in records:
            record_key = record.record_key or f"chapter:{int(record.chapter_id)}"
            point_id = int(hashlib.sha256(
                f"{record.owner_scope}:{record.book_id}:{record.knowledge_version}:{record_key}".encode()
            ).hexdigest()[:15], 16)
            payload = dict(record.payload or {})
            payload.setdefault("record_key", record_key)
            points.append({
                "id": point_id,
                "vector": record.vector,
                "payload": {
                    **payload,
                    "owner_scope": record.owner_scope,
                    "book_id": record.book_id,
                    "chapter_id": record.chapter_id,
                    "knowledge_version": record.knowledge_version,
                    "record_key": record_key,
                },
            })
        response = await self._client.put(
            f"{self._endpoint}/collections/{self._collection}/points",
            headers=self._headers(),
            json={"points": points},
        )
        if response.status_code >= 400:
            raise VectorStoreUnavailable(f"Qdrant upsert failed: HTTP {response.status_code}")
        return len(points)

    async def search(self, owner_scope: str, book_id: int, knowledge_version: str, query_vector: list[float], top_k: int) -> list[VectorRecord]:
        body = {
            "vector": query_vector,
            "limit": top_k,
            "with_payload": True,
            "filter": {"must": [
                {"key": "owner_scope", "match": {"value": owner_scope}},
                {"key": "book_id", "match": {"value": book_id}},
                {"key": "knowledge_version", "match": {"value": knowledge_version}},
            ]},
        }
        response = await self._client.post(
            f"{self._endpoint}/collections/{self._collection}/points/search",
            headers=self._headers(),
            json=body,
        )
        if response.status_code >= 400:
            raise VectorStoreUnavailable(f"Qdrant search failed: HTTP {response.status_code}")
        payload = response.json()
        results = payload.get("result", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise VectorStoreUnavailable("Qdrant search returned an invalid result shape")
        output = []
        for item in results:
            if not isinstance(item, dict):
                raise VectorStoreUnavailable("Qdrant search returned an invalid result item")
            item_payload = item.get("payload") or {}
            if not isinstance(item_payload, dict):
                raise VectorStoreUnavailable("Qdrant search returned an invalid payload shape")
            record_key = str(item_payload.get("record_key") or f"chapter:{int(item_payload.get('chapter_id', 0))}")
            output.append(VectorRecord(
                owner_scope=str(item_payload.get("owner_scope", owner_scope)),
                book_id=int(item_payload.get("book_id", book_id)),
                chapter_id=int(item_payload.get("chapter_id", 0)),
                knowledge_version=str(item_payload.get("knowledge_version", knowledge_version)),
                vector=[],
                payload={key: value for key, value in item_payload.items() if key not in {"owner_scope", "book_id", "chapter_id", "knowledge_version"}},
                score=float(item.get("score", 0.0)),
                record_key=record_key,
            ))
        return output

    async def delete_book(self, owner_scope: str, book_id: int, knowledge_version: str | None = None) -> int:
        must = [
            {"key": "owner_scope", "match": {"value": owner_scope}},
            {"key": "book_id", "match": {"value": book_id}},
        ]
        if knowledge_version is not None:
            must.append({"key": "knowledge_version", "match": {"value": knowledge_version}})
        response = await self._client.post(
            f"{self._endpoint}/collections/{self._collection}/points/delete",
            headers=self._headers(),
            json={"filter": {"must": must}},
        )
        if response.status_code >= 400:
            raise VectorStoreUnavailable(f"Qdrant delete failed: HTTP {response.status_code}")
        return 1

    async def delete_chapter(
        self,
        owner_scope: str,
        book_id: int,
        chapter_id: int,
        knowledge_version: str | None = None,
    ) -> int:
        must = [
            {"key": "owner_scope", "match": {"value": owner_scope}},
            {"key": "book_id", "match": {"value": book_id}},
            {"key": "chapter_id", "match": {"value": chapter_id}},
        ]
        if knowledge_version is not None:
            must.append({"key": "knowledge_version", "match": {"value": knowledge_version}})
        response = await self._client.post(
            f"{self._endpoint}/collections/{self._collection}/points/delete",
            headers=self._headers(),
            json={"filter": {"must": must}},
        )
        if response.status_code >= 400:
            raise VectorStoreUnavailable(f"Qdrant chapter delete failed: HTTP {response.status_code}")
        return 1

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get(
                f"{self._endpoint}/collections/{self._collection}", headers=self._headers()
            )
            return {"enabled": response.status_code < 400, "backend": "qdrant", "status_code": response.status_code}
        except Exception as exc:
            return {"enabled": False, "backend": "qdrant", "error": str(exc)[:200]}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
