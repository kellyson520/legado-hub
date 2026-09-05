"""Strict, evidence-bound validation for LLM novel extraction output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities.novel import EventType, RelationType, StateField


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)


class StructuredRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity: str = Field(min_length=1, max_length=200)
    target_entity: str = Field(min_length=1, max_length=200)
    relation_type: RelationType
    description: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(min_length=1, max_length=20)


class StructuredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int = Field(gt=0)
    event_type: EventType
    description: str = Field(min_length=1, max_length=2000)
    participants: list[str] = Field(default_factory=list, max_length=50)
    location: str = ""
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(min_length=1, max_length=20)


class StructuredStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_name: str = Field(min_length=1, max_length=200)
    chapter_id: int = Field(gt=0)
    field_name: StateField
    before_value: str = ""
    after_value: str = ""
    trigger_event: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(min_length=1, max_length=20)


class StructuredNovelExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    relationships: list[StructuredRelationship] = Field(default_factory=list, max_length=100)
    events: list[StructuredEvent] = Field(default_factory=list, max_length=100)
    state_changes: list[StructuredStateChange] = Field(default_factory=list, max_length=100)
    arc_tag: str = Field(default="", max_length=200)
    arc_summary: str = Field(default="", max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)


class StructuredExtractionError(ValueError):
    code = "structured_extraction_invalid"


class StructuredExtractor:
    """Validate and bind model output to the chapter that produced it."""

    model = StructuredNovelExtraction

    @classmethod
    def parse(
        cls,
        payload: Any,
        *,
        chapter_id: int,
        chapter_text: str,
    ) -> StructuredNovelExtraction:
        try:
            parsed = cls.model.model_validate(payload)
        except Exception:
            # Preserve Pydantic ValidationError for callers that need field
            # details; the typed wrapper is available for evidence failures.
            raise

        evidence = list(parsed.evidence)
        for item in parsed.relationships:
            evidence.extend(item.evidence)
        for item in parsed.events:
            evidence.extend(item.evidence)
        for item in parsed.state_changes:
            evidence.extend(item.evidence)

        for item in evidence:
            if item.chapter_id != int(chapter_id):
                raise StructuredExtractionError(
                    f"evidence chapter_id {item.chapter_id} is not bound to chapter {chapter_id}"
                )
            if item.text not in chapter_text:
                raise StructuredExtractionError("evidence text is not present in the chapter")
        return parsed

    validate = parse


# Compatibility names for integrations that use the domain noun first.
NovelStructuredExtraction = StructuredNovelExtraction
NovelEvidence = Evidence
