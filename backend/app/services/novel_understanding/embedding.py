"""
Embedding 适配器

支持：
1. 外部 API（OpenAI 兼容格式）- 需要配置 LLM_API_URL/KEY
2. 本地 fallback（Hash-based 伪向量）- 无 API 时兜底
"""

import hashlib
import json
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    text: str
    vector: List[float]
    source: str  # "api" / "local_hash"


class EmbeddingAdapter:
    """Embedding 适配器"""

    DIMENSION = 384  # 本地 hash 向量维度

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key

    async def embed(self, text: str) -> EmbeddingResult:
        """获取文本的向量表示"""
        if self.api_url and self.api_key:
            try:
                vector = await self._call_api(text)
                return EmbeddingResult(text=text, vector=vector, source="api")
            except Exception:
                pass  # fallback 到本地

        vector = self._local_hash_embedding(text)
        return EmbeddingResult(text=text, vector=vector, source="local_hash")

    async def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """批量获取向量"""
        results = []
        for text in texts:
            result = await self.embed(text)
            results.append(result)
        return results

    async def _call_api(self, text: str) -> List[float]:
        """调用外部 Embedding API"""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            payload = {
                "model": "text-embedding-3-small",
                "input": text[:8000],
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with session.post(self.api_url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["data"][0]["embedding"]
                raise Exception(f"API error: {resp.status}")

    @classmethod
    def _local_hash_embedding(cls, text: str) -> List[float]:
        """基于哈希的伪向量（确定性、快速、无外部依赖）"""
        # 使用多个哈希函数生成固定维度向量
        vector = []
        for i in range(cls.DIMENSION):
            seed = f"{i}:{text}"
            hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
            # 归一化到 [-1, 1]
            normalized = (hash_val % 20000) / 10000 - 1
            vector.append(normalized)
        return vector

    @classmethod
    def cosine_similarity(cls, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            raise ValueError("Vectors must have same dimension")
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
