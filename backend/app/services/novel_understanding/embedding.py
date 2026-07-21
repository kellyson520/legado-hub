"""Embedding adapter for the shared Provider route.

The default no-provider mode remains useful for deterministic unit fixtures,
but its hash vectors are explicitly marked non-semantic and must not be used
as production semantic retrieval evidence.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from typing import Any, List


class EmbeddingUnavailable(RuntimeError):
    code = "embedding_unavailable"


@dataclass
class EmbeddingResult:
    text: str
    vector: List[float]
    source: str  # "provider" / "local_hash"
    model: str = ""
    dimension: int = 0
    cache_hit: bool = False
    semantic: bool = False
    provider_name: str = ""
    usage: dict[str, Any] | None = None


class EmbeddingAdapter:
    """Route embeddings through ProviderPlatformService when configured."""

    DIMENSION = 384  # deterministic fixture fallback only

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        *,
        provider=None,
        embedding_provider=None,
        provider_platform=None,
        owner_scope: str = "legacy",
        book_id: int | None = None,
        knowledge_version: str = "",
        model: str | None = None,
        batch_size: int = 32,
        quota_scope: tuple[str, str] | None = None,
        cache_service=None,
        cache=None,
        prompt_version: str = "embedding-v1",
        toolset_version: str = "embedding",
    ):
        # api_url/api_key remain accepted for source compatibility, but calls
        # intentionally do not bypass the shared provider boundary anymore.
        self.api_url = api_url
        self.api_key = api_key
        self._provider = provider or embedding_provider or provider_platform
        self.owner_scope = owner_scope or "legacy"
        self.book_id = book_id
        self.knowledge_version = knowledge_version or ""
        self.model = (model or "").strip() or None
        self.batch_size = max(1, int(batch_size))
        self.quota_scope = quota_scope or ("novel", self.owner_scope)
        self._cache_service = cache_service or cache
        self.prompt_version = prompt_version
        self.toolset_version = toolset_version

    async def embed(self, text: str) -> EmbeddingResult:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        normalized = [str(text) for text in texts]
        if self._provider is None:
            return [
                EmbeddingResult(
                    text=text,
                    vector=self._local_hash_embedding(text),
                    source="local_hash",
                    model="",
                    dimension=self.DIMENSION,
                    semantic=False,
                )
                for text in normalized
            ]

        cached: list[EmbeddingResult | None] = [None] * len(normalized)
        missing_positions: list[int] = []
        cache_keys: dict[int, str] = {}
        for index, text in enumerate(normalized):
            key = self._cache_key(text)
            if key is None:
                missing_positions.append(index)
                continue
            cache_keys[index] = key
            value = await self._cache_get(key)
            if value is None:
                missing_positions.append(index)
            else:
                cached[index] = self._from_cached(text, value)

        for start in range(0, len(missing_positions), self.batch_size):
            positions = missing_positions[start : start + self.batch_size]
            batch = [normalized[index] for index in positions]
            try:
                response = await self._invoke_provider(batch)
                vectors = self._parse_provider_response(response, len(batch))
            except EmbeddingUnavailable:
                raise
            except Exception as exc:
                raise EmbeddingUnavailable(f"embedding provider failed: {str(exc)[:200]}") from exc

            for position, vector_data in zip(positions, vectors):
                result = EmbeddingResult(
                    text=normalized[position],
                    vector=vector_data["vector"],
                    source="provider",
                    model=vector_data["model"],
                    dimension=len(vector_data["vector"]),
                    cache_hit=False,
                    semantic=True,
                    provider_name=vector_data["provider_name"],
                    usage=vector_data["usage"],
                )
                cached[position] = result
                key = cache_keys.get(position)
                if key is not None:
                    await self._cache_set(key, self._to_cached(result))

        return [item for item in cached if item is not None]

    async def _invoke_provider(self, texts: list[str]):
        provider = self._provider
        payload = {"input": texts}
        method = getattr(provider, "invoke_novel_embedding", None)
        if callable(method):
            return await method(
                owner_scope=self.owner_scope,
                model=self.model,
                payload=payload,
                quota_scope=self.quota_scope,
            )
        method = getattr(provider, "invoke_embedding", None)
        if callable(method):
            return await method(model=self.model or "", payload=payload)
        if callable(provider):
            try:
                parameter_names = set(inspect.signature(provider).parameters)
            except (TypeError, ValueError):
                parameter_names = set()
            if {"owner_scope", "model", "payload", "quota_scope"}.issubset(parameter_names):
                result = provider(
                    owner_scope=self.owner_scope,
                    model=self.model,
                    payload=payload,
                    quota_scope=self.quota_scope,
                )
            else:
                result = provider(texts)
            if inspect.isawaitable(result):
                return await result
            return result
        raise EmbeddingUnavailable("embedding provider is not callable")

    @staticmethod
    def _parse_provider_response(response: dict[str, Any], expected: int) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            raise EmbeddingUnavailable("embedding provider returned an invalid response")
        data = response.get("data") or response.get("embeddings") or []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or len(data) != expected:
            raise EmbeddingUnavailable("embedding provider returned an unexpected vector count")
        ordered = sorted(
            enumerate(data),
            key=lambda item: int(item[1].get("index", item[0])) if isinstance(item[1], dict) else item[0],
        )
        output = []
        for _, item in ordered:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise EmbeddingUnavailable("embedding provider returned an invalid vector")
            try:
                normalized = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingUnavailable("embedding provider returned non-numeric vector values") from exc
            output.append(
                {
                    "vector": normalized,
                    "model": str(response.get("model") or ""),
                    "provider_name": str(response.get("provider_name") or ""),
                    "usage": response.get("usage") or {},
                }
            )
        dimension = len(output[0]["vector"])
        if any(len(item["vector"]) != dimension for item in output):
            raise EmbeddingUnavailable("embedding provider returned inconsistent dimensions")
        return output

    def _cache_key(self, text: str) -> str | None:
        service = self._cache_service
        if service is None:
            return None
        key_builder = getattr(service, "key", None)
        if callable(key_builder):
            return key_builder(
                owner_scope=self.owner_scope,
                book_id=self.book_id,
                knowledge_version=self.knowledge_version,
                model=self.model or "route-default",
                task_type="embedding",
                query=text,
                prompt_version=self.prompt_version,
                toolset_version=self.toolset_version,
            )
        return "novel:embedding:" + hashlib.sha256(
            f"{self.owner_scope}\0{self.book_id}\0{self.knowledge_version}\0{text}".encode("utf-8")
        ).hexdigest()

    async def _cache_get(self, key: str):
        service = self._cache_service
        getter = getattr(service, "get", None)
        if callable(getter):
            return await getter(key)
        backend = getattr(service, "_cache", None)
        if backend is not None:
            return await backend.get(key)
        return None

    async def _cache_set(self, key: str, value: dict[str, Any]) -> None:
        service = self._cache_service
        setter = getattr(service, "set", None)
        if callable(setter):
            await setter(key, value)
            return
        backend = getattr(service, "_cache", None)
        if backend is not None:
            await backend.set(key, value, expire=3600)

    @staticmethod
    def _to_cached(result: EmbeddingResult) -> dict[str, Any]:
        return {
            "vector": result.vector,
            "model": result.model,
            "provider_name": result.provider_name,
            "usage": result.usage or {},
            "semantic": result.semantic,
        }

    @staticmethod
    def _from_cached(text: str, value) -> EmbeddingResult:
        if isinstance(value, EmbeddingResult):
            value.text = text
            value.cache_hit = True
            return value
        vector = [float(item) for item in value.get("vector", [])]
        return EmbeddingResult(
            text=text,
            vector=vector,
            source="provider" if value.get("semantic", True) else "local_hash",
            model=str(value.get("model") or ""),
            dimension=len(vector),
            cache_hit=True,
            semantic=bool(value.get("semantic", True)),
            provider_name=str(value.get("provider_name") or ""),
            usage=value.get("usage") or {},
        )

    @classmethod
    def _local_hash_embedding(cls, text: str) -> List[float]:
        """基于哈希的确定性向量；仅用于测试/离线标识，不具备语义含义。"""
        vector = []
        for i in range(cls.DIMENSION):
            seed = f"{i}:{text}"
            hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
            vector.append((hash_val % 20000) / 10000 - 1)
        return vector

    @classmethod
    def cosine_similarity(cls, a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            raise ValueError("Vectors must have same dimension")
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
