"""Compatibility facade for deterministic novel entity extraction."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from app.domain.entities.novel import NovelEntity, NovelRelationship

from .candidate_extractor import CandidateExtractor


class AutoExtractor:
    """Run local extraction without invoking an external model."""

    COMMON_SURNAMES = CandidateExtractor.COMMON_SURNAMES
    LOCATION_KEYWORDS = list(CandidateExtractor.LOCATION_SUFFIXES)
    FACTION_KEYWORDS = list(CandidateExtractor.FACTION_SUFFIXES)

    def __init__(self, learning_profile: dict | None = None):
        self.extracted_entities: Dict[str, NovelEntity] = {}
        self.extracted_relations: List[NovelRelationship] = []
        self._entity_mentions = defaultdict(list)
        self._candidate_extractor = CandidateExtractor(learning_profile)

    def set_learning_profile(self, learning_profile: dict | None = None) -> None:
        self._candidate_extractor.set_learning_profile(learning_profile)

    def extract_from_chapter(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
    ) -> Tuple[List[NovelEntity], List[NovelRelationship]]:
        del chapter_title
        return self.extract_with_evidence(book_id, chapter_num, "", chapter_content)

    def extract_with_evidence(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
        *,
        chapter_id: int | None = None,
    ) -> Tuple[List[NovelEntity], List[NovelRelationship]]:
        del chapter_title
        entities, relationships = self._candidate_extractor.extract(
            book_id,
            chapter_num,
            "",
            chapter_content,
            chapter_id=chapter_id,
        )
        for entity in entities:
            self._entity_mentions[entity.name].append(chapter_num)
        self.extracted_relations.extend(relationships)
        return entities, relationships

    def merge_entities(self, all_entities: List[NovelEntity]) -> List[NovelEntity]:
        """Merge chapter-local entities while preserving evidence and aliases."""
        entity_map: Dict[tuple[int, str, str], NovelEntity] = {}
        for entity in all_entities:
            entity_type = getattr(entity.entity_type, "value", entity.entity_type)
            key = (int(entity.book_id), entity.name.strip(), str(entity_type))
            existing = entity_map.get(key)
            if existing is None:
                entity_map[key] = entity
                continue
            existing.first_appearance_ch = min(existing.first_appearance_ch, entity.first_appearance_ch)
            existing.last_appearance_ch = max(existing.last_appearance_ch, entity.last_appearance_ch)
            existing.appearance_count += entity.appearance_count
            existing.importance_score = max(existing.importance_score, entity.importance_score)
            existing.aliases = list(dict.fromkeys([*(existing.aliases or []), *(entity.aliases or [])]))
            if not existing.description and entity.description:
                existing.description = entity.description
            existing.attributes = self._merge_attributes(existing.attributes, entity.attributes)
        return list(entity_map.values())

    @staticmethod
    def _merge_attributes(left: dict, right: dict) -> dict:
        result = dict(left or {})
        for key, value in (right or {}).items():
            if key == "evidence":
                current = list(result.get(key) or [])
                seen = {(item.get("chapter_id"), item.get("start_offset"), item.get("text")) for item in current if isinstance(item, dict)}
                for item in value or []:
                    marker = (item.get("chapter_id"), item.get("start_offset"), item.get("text")) if isinstance(item, dict) else (None, None, str(item))
                    if marker not in seen:
                        current.append(item)
                        seen.add(marker)
                result[key] = current[:12]
            elif key == "confidence":
                result[key] = max(float(result.get(key) or 0), float(value or 0))
            elif value not in (None, "", [], {}):
                result[key] = value
        return result
