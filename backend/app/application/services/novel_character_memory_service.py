from __future__ import annotations

import math
import re
from typing import Any, ClassVar

from app.application.services.novel_understanding.embedding import EmbeddingAdapter


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class NovelCharacterMemoryService:
    """Stores chapter-level memory scenes for characters and provides hybrid vector retrieval."""

    # In-memory store keyed by (book_id, character_name) -> list of memory dicts
    _STORE: ClassVar[dict[tuple[int, str], list[dict[str, Any]]]] = {}

    def __init__(self, embedding_adapter: EmbeddingAdapter | None = None):
        self._embedder = embedding_adapter or EmbeddingAdapter()

    async def index_character_scenes(
        self,
        book_id: int,
        chapters: list[dict[str, Any]],
        character_names: list[str],
    ) -> int:
        """Extracts character-centric scenes, embeds them, and indexes them into vector memory."""
        split_pattern = re.compile(r"[。！？\n；]")
        indexed_total = 0

        for char_name in character_names:
            key = (book_id, char_name)
            memories: list[dict[str, Any]] = []

            for chapter in chapters:
                content = str(chapter.get("content", ""))
                chapter_index = int(chapter.get("chapter_index", 0))
                chapter_title = str(chapter.get("title", ""))

                sentences = [s.strip() for s in split_pattern.split(content) if s.strip()]
                relevant: list[str] = []
                for s in sentences:
                    if char_name in s or any(kw in s for kw in ("他", "她", "自己")):
                        relevant.append(s)

                if not relevant:
                    continue

                scene_text = " ".join(relevant[:5])
                res = await self._embedder.embed(scene_text)
                vector = res.vector

                memories.append({
                    "book_id": book_id,
                    "character_name": char_name,
                    "chapter_index": chapter_index,
                    "chapter_title": chapter_title,
                    "excerpt": scene_text[:280],
                    "vector": vector,
                })
                indexed_total += 1

            self._STORE[key] = memories

        return indexed_total

    async def hybrid_query(
        self,
        book_id: int,
        character_name: str,
        query_text: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval: filters character memory slices, computes cosine similarity and keyword overlap."""
        key = (book_id, character_name)
        memories = self._STORE.get(key, [])
        if not memories:
            return []

        query_res = await self._embedder.embed(query_text)
        q_vec = query_res.vector

        scored_results: list[dict[str, Any]] = []
        query_tokens = [t for t in re.findall(r"[\u4e00-\u9fff]{2,4}|[a-zA-Z0-9]+", query_text) if len(t) >= 2]

        for m in memories:
            cos_sim = _cosine(q_vec, m["vector"])
            # Keyword overlap boost
            overlap_count = sum(1 for tok in query_tokens if tok in m["excerpt"])
            keyword_score = min(overlap_count * 0.25, 0.5)

            final_score = round(cos_sim * 0.5 + keyword_score * 0.5, 3)
            scored_results.append({
                "chapter_index": m["chapter_index"],
                "chapter_title": m["chapter_title"],
                "excerpt": m["excerpt"],
                "score": final_score,
                "keywords": [tok for tok in query_tokens if tok in m["excerpt"]],
            })

        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]
