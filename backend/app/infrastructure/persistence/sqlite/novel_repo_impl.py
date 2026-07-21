"""SQLite implementation of the owner-scoped novel repository.

The public methods accept the new ``owner_scope``-first contract.  Calls made
by the original novel importer are still accepted and are treated as the
``legacy`` scope so existing integrations can migrate incrementally.
"""

from __future__ import annotations

import json
from typing import List, Optional

from app.domain.entities.novel import (
    ChapterFingerprint,
    EntityType,
    EventType,
    IngestSource,
    NovelBook,
    NovelChapter,
    NovelChapterMirror,
    NovelEntity,
    NovelEvent,
    NovelRelationship,
    NovelSourceMirror,
    NovelStateChange,
    NovelStatus,
    RelationType,
    StateField,
)
from app.domain.entities.novel_runtime import NovelIndexState, NovelReadingProgress
from app.domain.repositories.novel_repo import NovelRepository
from app.domain.value_objects import OwnerScope


LEGACY_SCOPE = str(OwnerScope.legacy())


def _scope(value: str | OwnerScope | None) -> str:
    if value is None:
        return LEGACY_SCOPE
    return str(value)


class SqliteNovelRepository(NovelRepository):
    def __init__(self, db):
        self._db = db

    # --- argument compatibility helpers ---------------------------------
    @staticmethod
    def _book_scope(scope_or_book, book: NovelBook | None) -> tuple[str, NovelBook]:
        if book is None:
            if not isinstance(scope_or_book, NovelBook):
                raise TypeError("save_book expects (owner_scope, book) or (book)")
            return _scope(scope_or_book.owner_scope), scope_or_book
        return _scope(scope_or_book), book

    @staticmethod
    def _scope_and_id(scope_or_id, value: int | None) -> tuple[str, int]:
        if value is None:
            return LEGACY_SCOPE, int(scope_or_id)
        return _scope(scope_or_id), int(value)

    async def _require_book(self, owner_scope: str, book_id: int) -> None:
        async with self._db.execute(
            "SELECT id FROM novels WHERE owner_scope=? AND id=?",
            (_scope(owner_scope), book_id),
        ) as cursor:
            if await cursor.fetchone() is None:
                raise ValueError(f"book {book_id} does not belong to owner scope {_scope(owner_scope)!r}")

    async def _book_exists_for_chapter(self, owner_scope: str, chapter_id: int) -> bool:
        async with self._db.execute(
            """SELECT 1 FROM novel_chapters c
               JOIN novels n ON n.id=c.book_id
               WHERE c.id=? AND n.owner_scope=?""",
            (chapter_id, _scope(owner_scope)),
        ) as cursor:
            return await cursor.fetchone() is not None

    # --- NovelBook -------------------------------------------------------
    async def save_book(self, owner_scope: str | NovelBook, book: NovelBook | None = None) -> NovelBook:
        scope, book = self._book_scope(owner_scope, book)
        book.owner_scope = scope
        await self._db.execute(
            """INSERT INTO novels (
                book_url, book_name, author, source_name, total_chapters, total_words,
                status, source_type, ingest_progress, ingest_error_msg,
                character_count, entity_count, event_count, relationship_count,
                summary_global, owner_scope
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_scope, book_url) DO UPDATE SET
                book_name=excluded.book_name,
                author=excluded.author,
                source_name=excluded.source_name,
                total_chapters=excluded.total_chapters,
                total_words=excluded.total_words,
                status=excluded.status,
                source_type=excluded.source_type,
                ingest_progress=excluded.ingest_progress,
                ingest_error_msg=excluded.ingest_error_msg,
                character_count=excluded.character_count,
                entity_count=excluded.entity_count,
                event_count=excluded.event_count,
                relationship_count=excluded.relationship_count,
                summary_global=excluded.summary_global,
                updated_at=CURRENT_TIMESTAMP""",
            (
                book.book_url,
                book.book_name,
                book.author,
                book.source_name,
                book.total_chapters,
                book.total_words,
                book.status.value,
                book.source_type.value,
                book.ingest_progress,
                book.ingest_error_msg,
                book.character_count,
                book.entity_count,
                book.event_count,
                book.relationship_count,
                book.summary_global,
                scope,
            ),
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT * FROM novels WHERE owner_scope=? AND book_url=?",
            (scope, book.book_url),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("novel book was not persisted")
        saved = self._row_to_book(row)
        book.__dict__.update(saved.__dict__)
        return book

    async def get_book_by_id(self, owner_scope: str | int, book_id: int | None = None) -> Optional[NovelBook]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        async with self._db.execute(
            "SELECT * FROM novels WHERE owner_scope=? AND id=?", (scope, book_id)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_book(row) if row else None

    async def get_book(self, owner_scope: str | int, book_id: int | None = None) -> Optional[NovelBook]:
        return await self.get_book_by_id(owner_scope, book_id)

    async def get_book_by_url(self, owner_scope: str, book_url: str | None = None) -> Optional[NovelBook]:
        if book_url is None:
            book_url = owner_scope
            owner_scope = LEGACY_SCOPE
        async with self._db.execute(
            "SELECT * FROM novels WHERE owner_scope=? AND book_url=?",
            (_scope(owner_scope), book_url),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_book(row) if row else None

    async def claim_legacy_scope(self, owner_scope: str) -> dict:
        target_scope = _scope(owner_scope)
        if target_scope == LEGACY_SCOPE:
            raise ValueError("legacy scope cannot be claimed by itself")
        async with self._db.execute(
            """SELECT book_url FROM novels
               WHERE owner_scope=? AND book_url IN (
                   SELECT book_url FROM novels WHERE owner_scope=?
               )
               LIMIT 1""",
            (target_scope, LEGACY_SCOPE),
        ) as cursor:
            conflict = await cursor.fetchone()
        if conflict is not None:
            raise ValueError(f"legacy book conflicts with an existing book URL: {conflict[0]}")

        counts: dict[str, int] = {}
        try:
            for table in (
                "novels",
                "novel_index_states",
                "novel_reading_progress",
                "novel_vectors",
                "novel_model_preferences",
            ):
                cursor = await self._db.execute(
                    f"UPDATE {table} SET owner_scope=? WHERE owner_scope=?",
                    (target_scope, LEGACY_SCOPE),
                )
                counts[table] = max(cursor.rowcount, 0)
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        counts["books"] = counts.pop("novels", 0)
        return counts

    async def list_books(
        self,
        owner_scope: str | NovelStatus | None = LEGACY_SCOPE,
        status: Optional[NovelStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[NovelBook]:
        # Legacy positional form: list_books(status, limit, offset).
        if isinstance(owner_scope, NovelStatus):
            legacy_status = owner_scope
            legacy_limit = status if isinstance(status, int) else 20
            legacy_offset = limit if isinstance(limit, int) and not isinstance(limit, bool) else 0
            owner_scope, status, limit, offset = LEGACY_SCOPE, legacy_status, legacy_limit, legacy_offset
        conditions = ["owner_scope=?"]
        params: list[object] = [_scope(owner_scope)]
        if status is not None:
            conditions.append("status=?")
            params.append(status.value)
        params.extend([limit, offset])
        async with self._db.execute(
            f"SELECT * FROM novels WHERE {' AND '.join(conditions)} "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_book(row) for row in rows]

    async def count_books(
        self,
        owner_scope: str | NovelStatus | None = LEGACY_SCOPE,
        status: Optional[NovelStatus] = None,
    ) -> int:
        if isinstance(owner_scope, NovelStatus):
            status, owner_scope = owner_scope, LEGACY_SCOPE
        conditions = ["owner_scope=?"]
        params: list[object] = [_scope(owner_scope)]
        if status is not None:
            conditions.append("status=?")
            params.append(status.value)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM novels WHERE {' AND '.join(conditions)}", params
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def update_book_status(
        self,
        owner_scope: str | int,
        book_id: int | NovelStatus,
        status: NovelStatus | None = None,
        progress: Optional[float] = None,
        error_msg: Optional[str] = None,
    ) -> bool:
        if status is None and isinstance(book_id, NovelStatus):
            status, book_id, owner_scope = book_id, int(owner_scope), LEGACY_SCOPE
        if status is None:
            raise TypeError("status is required")
        fields = ["status=?"]
        params: list[object] = [status.value]
        if progress is not None:
            fields.append("ingest_progress=?")
            params.append(max(0.0, min(1.0, float(progress))))
        if error_msg is not None:
            fields.append("ingest_error_msg=?")
            params.append(error_msg)
        params.extend([_scope(owner_scope), int(book_id)])
        cursor = await self._db.execute(
            f"UPDATE novels SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP "
            "WHERE owner_scope=? AND id=?",
            params,
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def update_book_summary(self, owner_scope: str | int, book_id: int | str, summary: str | None = None) -> bool:
        if summary is None:
            summary, book_id, owner_scope = str(book_id), int(owner_scope), LEGACY_SCOPE
        cursor = await self._db.execute(
            "UPDATE novels SET summary_global=?, updated_at=CURRENT_TIMESTAMP WHERE owner_scope=? AND id=?",
            (summary, _scope(owner_scope), int(book_id)),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_book(self, owner_scope: str | int, book_id: int | None = None) -> bool:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        cursor = await self._db.execute(
            "DELETE FROM novels WHERE owner_scope=? AND id=?", (scope, book_id)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # --- NovelChapter ----------------------------------------------------
    async def save_chapter(self, owner_scope: str | NovelChapter, chapter: NovelChapter | None = None) -> NovelChapter:
        if chapter is None:
            chapter = owner_scope
            owner_scope = LEGACY_SCOPE
        scope = _scope(owner_scope)
        await self._require_book(scope, chapter.book_id)
        cursor = await self._db.execute(
            """INSERT INTO novel_chapters (
                book_id, canonical_type, canonical_num, canonical_full, raw_title,
                parsed_title_core, raw_chapter_num, source_volume, chapter_num,
                chapter_title, word_count, raw_text_hash, raw_text, quality_score,
                summary, key_events, character_appearances, location_appearances,
                mood_tags, arc_tag, arc_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chapter.book_id,
                chapter.canonical_type,
                chapter.canonical_num,
                chapter.canonical_full,
                chapter.raw_title,
                chapter.parsed_title_core,
                chapter.raw_chapter_num,
                chapter.source_volume,
                chapter.chapter_num,
                chapter.chapter_title,
                chapter.word_count,
                chapter.raw_text_hash,
                chapter.raw_text,
                chapter.quality_score,
                chapter.summary,
                json.dumps(chapter.key_events, ensure_ascii=False),
                json.dumps(chapter.character_appearances, ensure_ascii=False),
                json.dumps(chapter.location_appearances, ensure_ascii=False),
                json.dumps(chapter.mood_tags, ensure_ascii=False),
                chapter.arc_tag,
                chapter.arc_summary,
            ),
        )
        await self._db.commit()
        chapter.id = cursor.lastrowid
        return chapter

    async def save_chapters_batch(
        self, owner_scope: str | List[NovelChapter], chapters: List[NovelChapter] | None = None
    ) -> int:
        if chapters is None:
            chapters, owner_scope = owner_scope, LEGACY_SCOPE
        for chapter in chapters:
            await self.save_chapter(owner_scope, chapter)
        return len(chapters)

    async def get_chapter_by_id(self, owner_scope: str | int, chapter_id: int | None = None) -> Optional[NovelChapter]:
        scope, chapter_id = self._scope_and_id(owner_scope, chapter_id)
        async with self._db.execute(
            """SELECT c.* FROM novel_chapters c JOIN novels n ON n.id=c.book_id
               WHERE n.owner_scope=? AND c.id=?""",
            (scope, chapter_id),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_chapter(row) if row else None

    async def get_chapter(self, owner_scope: str | int, chapter_id: int | None = None) -> Optional[NovelChapter]:
        return await self.get_chapter_by_id(owner_scope, chapter_id)

    async def get_chapters_by_book(
        self,
        owner_scope: str | int,
        book_id: int | None = None,
        start_num: int = 1,
        end_num: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[NovelChapter]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        conditions = ["n.owner_scope=?", "c.book_id=?", "c.canonical_num >= ?"]
        params: list[object] = [scope, book_id, start_num]
        if end_num is not None:
            conditions.append("c.canonical_num <= ?")
            params.append(end_num)
        params.extend([limit, offset])
        async with self._db.execute(
            f"SELECT c.* FROM novel_chapters c JOIN novels n ON n.id=c.book_id "
            f"WHERE {' AND '.join(conditions)} ORDER BY c.canonical_num LIMIT ? OFFSET ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_chapter(row) for row in rows]

    async def count_chapters(self, owner_scope: str | int, book_id: int | None = None) -> int:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        async with self._db.execute(
            """SELECT COUNT(*) FROM novel_chapters c JOIN novels n ON n.id=c.book_id
               WHERE n.owner_scope=? AND c.book_id=?""",
            (scope, book_id),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def update_chapter_summary(
        self,
        owner_scope: str | int,
        chapter_id: int | str,
        summary: str | List[str],
        key_events: List[str] | None = None,
    ) -> bool:
        if key_events is None:
            key_events, summary, chapter_id, owner_scope = summary, str(chapter_id), int(owner_scope), LEGACY_SCOPE
        cursor = await self._db.execute(
            """UPDATE novel_chapters SET summary=?, key_events=? WHERE id=? AND book_id IN (
                SELECT n.id FROM novels n WHERE n.owner_scope=?
            )""",
            (summary, json.dumps(key_events, ensure_ascii=False), int(chapter_id), _scope(owner_scope)),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def update_chapter_content(
        self,
        owner_scope: str | int,
        chapter_id: int | str,
        content: str,
        quality_score: Optional[float] = None,
    ) -> bool:
        if isinstance(owner_scope, int):
            quality_score, content, chapter_id, owner_scope = content if isinstance(content, float) else quality_score, str(chapter_id), int(owner_scope), LEGACY_SCOPE
        fields = ["raw_text=?", "word_count=?", "raw_text_hash=?"]
        params: list[object] = [content, len(content), _hash_text(content)]
        if quality_score is not None:
            fields.append("quality_score=?")
            params.append(quality_score)
        params.extend([int(chapter_id), _scope(owner_scope)])
        cursor = await self._db.execute(
            f"UPDATE novel_chapters SET {', '.join(fields)} WHERE id=? AND book_id IN "
            "(SELECT n.id FROM novels n WHERE n.owner_scope=?)",
            params,
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # --- NovelEntity -----------------------------------------------------
    async def save_entity(self, owner_scope: str | NovelEntity, entity: NovelEntity | None = None) -> NovelEntity:
        if entity is None:
            entity, owner_scope = owner_scope, LEGACY_SCOPE
        scope = _scope(owner_scope)
        await self._require_book(scope, entity.book_id)
        cursor = await self._db.execute(
            """INSERT INTO novel_entities (
                book_id, name, aliases, entity_type, description,
                first_appearance_ch, last_appearance_ch, appearance_count,
                importance_score, attributes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id, name) DO UPDATE SET
                aliases=excluded.aliases,
                entity_type=excluded.entity_type,
                description=excluded.description,
                first_appearance_ch=excluded.first_appearance_ch,
                last_appearance_ch=excluded.last_appearance_ch,
                appearance_count=excluded.appearance_count,
                importance_score=excluded.importance_score,
                attributes=excluded.attributes""",
            (
                entity.book_id,
                entity.name,
                json.dumps(entity.aliases, ensure_ascii=False),
                entity.entity_type.value,
                entity.description,
                entity.first_appearance_ch,
                entity.last_appearance_ch,
                entity.appearance_count,
                entity.importance_score,
                json.dumps(entity.attributes, ensure_ascii=False),
            ),
        )
        await self._db.commit()
        if entity.id == 0:
            async with self._db.execute(
                "SELECT id FROM novel_entities WHERE book_id=? AND name=?",
                (entity.book_id, entity.name),
            ) as row_cursor:
                row = await row_cursor.fetchone()
            entity.id = row[0] if row else cursor.lastrowid
        return entity

    async def save_entities_batch(
        self, owner_scope: str | List[NovelEntity], entities: List[NovelEntity] | None = None
    ) -> int:
        if entities is None:
            entities, owner_scope = owner_scope, LEGACY_SCOPE
        for entity in entities:
            await self.save_entity(owner_scope, entity)
        return len(entities)

    async def get_entity_by_id(self, owner_scope: str | int, entity_id: int | None = None) -> Optional[NovelEntity]:
        scope, entity_id = self._scope_and_id(owner_scope, entity_id)
        async with self._db.execute(
            """SELECT e.* FROM novel_entities e JOIN novels n ON n.id=e.book_id
               WHERE n.owner_scope=? AND e.id=?""",
            (scope, entity_id),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_entity(row) if row else None

    async def get_entity(self, owner_scope: str | int, entity_id: int | None = None) -> Optional[NovelEntity]:
        return await self.get_entity_by_id(owner_scope, entity_id)

    async def get_entity_by_name(
        self, owner_scope: str | int, book_id: int | str, name: str | None = None
    ) -> Optional[NovelEntity]:
        if name is None:
            name, book_id, owner_scope = str(book_id), int(owner_scope), LEGACY_SCOPE
        async with self._db.execute(
            """SELECT e.* FROM novel_entities e JOIN novels n ON n.id=e.book_id
               WHERE n.owner_scope=? AND e.book_id=? AND e.name=?""",
            (_scope(owner_scope), int(book_id), name),
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_entity(row) if row else None

    async def list_entities(
        self,
        owner_scope: str | int,
        book_id: int | EntityType | None = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[NovelEntity]:
        if isinstance(owner_scope, int):
            if isinstance(book_id, EntityType):
                entity_type, book_id = book_id, owner_scope
            elif book_id is None:
                book_id = owner_scope
            owner_scope = LEGACY_SCOPE
        conditions = ["n.owner_scope=?", "e.book_id=?"]
        params: list[object] = [_scope(owner_scope), int(book_id)]
        if entity_type is not None:
            conditions.append("e.entity_type=?")
            params.append(entity_type.value)
        params.extend([limit, offset])
        async with self._db.execute(
            f"SELECT e.* FROM novel_entities e JOIN novels n ON n.id=e.book_id "
            f"WHERE {' AND '.join(conditions)} ORDER BY e.importance_score DESC LIMIT ? OFFSET ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_entity(row) for row in rows]

    async def count_entities(
        self, owner_scope: str | int, book_id: int | EntityType | None = None, entity_type: Optional[EntityType] = None
    ) -> int:
        if isinstance(owner_scope, int):
            if isinstance(book_id, EntityType):
                entity_type, book_id = book_id, owner_scope
            elif book_id is None:
                book_id = owner_scope
            owner_scope = LEGACY_SCOPE
        conditions = ["n.owner_scope=?", "e.book_id=?"]
        params: list[object] = [_scope(owner_scope), int(book_id)]
        if entity_type is not None:
            conditions.append("e.entity_type=?")
            params.append(entity_type.value)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM novel_entities e JOIN novels n ON n.id=e.book_id WHERE {' AND '.join(conditions)}",
            params,
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0])

    async def get_entity_names_by_book(self, owner_scope: str | int, book_id: int | None = None) -> List[str]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        async with self._db.execute(
            """SELECT e.name FROM novel_entities e JOIN novels n ON n.id=e.book_id
               WHERE n.owner_scope=? AND e.book_id=? ORDER BY e.importance_score DESC""",
            (scope, book_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def search_entities(
        self,
        owner_scope: str | int,
        book_id: int | str,
        keyword: str | None = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 20,
    ) -> List[NovelEntity]:
        if keyword is None:
            keyword, book_id, owner_scope = str(book_id), int(owner_scope), LEGACY_SCOPE
        pattern = f"%{keyword}%"
        conditions = [
            "n.owner_scope=?",
            "e.book_id=?",
            "(e.name LIKE ? OR e.description LIKE ? OR e.aliases LIKE ?)",
        ]
        params: list[object] = [_scope(owner_scope), int(book_id), pattern, pattern, pattern]
        if entity_type is not None:
            conditions.append("e.entity_type=?")
            params.append(entity_type.value)
        params.append(limit)
        async with self._db.execute(
            f"SELECT e.* FROM novel_entities e JOIN novels n ON n.id=e.book_id WHERE {' AND '.join(conditions)} LIMIT ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_entity(row) for row in rows]

    # --- NovelRelationship ----------------------------------------------
    async def save_relationship(
        self, owner_scope: str | NovelRelationship, rel: NovelRelationship | None = None
    ) -> NovelRelationship:
        if rel is None:
            rel, owner_scope = owner_scope, LEGACY_SCOPE
        await self._require_book(_scope(owner_scope), rel.book_id)
        cursor = await self._db.execute(
            """INSERT INTO novel_relationships (
                book_id, source_entity, target_entity, relation_type, description,
                since_chapter, until_chapter, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel.book_id,
                rel.source_entity,
                rel.target_entity,
                rel.relation_type.value,
                rel.description,
                rel.since_chapter,
                rel.until_chapter,
                rel.confidence,
            ),
        )
        await self._db.commit()
        rel.id = cursor.lastrowid
        return rel

    async def save_relationships_batch(
        self, owner_scope: str | List[NovelRelationship], rels: List[NovelRelationship] | None = None
    ) -> int:
        if rels is None:
            rels, owner_scope = owner_scope, LEGACY_SCOPE
        for rel in rels:
            await self.save_relationship(owner_scope, rel)
        return len(rels)

    async def get_relationships_by_book(
        self, owner_scope: str | int, book_id: int | None = None, limit: int = 50
    ) -> List[NovelRelationship]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        async with self._db.execute(
            """SELECT r.* FROM novel_relationships r JOIN novels n ON n.id=r.book_id
               WHERE n.owner_scope=? AND r.book_id=? LIMIT ?""",
            (scope, book_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_relationship(row) for row in rows]

    async def get_relationships_by_entity(
        self, owner_scope: str | int, book_id: int | str, entity_name: str | None = None, limit: int = 50
    ) -> List[NovelRelationship]:
        if entity_name is None:
            entity_name, book_id, owner_scope = str(book_id), int(owner_scope), LEGACY_SCOPE
        async with self._db.execute(
            """SELECT r.* FROM novel_relationships r JOIN novels n ON n.id=r.book_id
               WHERE n.owner_scope=? AND r.book_id=?
               AND (r.source_entity=? OR r.target_entity=?) LIMIT ?""",
            (_scope(owner_scope), int(book_id), entity_name, entity_name, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_relationship(row) for row in rows]

    async def get_relationships(
        self, owner_scope: str | int, book_id: int | None = None, entity_name: Optional[str] = None, limit: int = 50
    ) -> List[NovelRelationship]:
        if book_id is None:
            book_id, owner_scope = int(owner_scope), LEGACY_SCOPE
        if entity_name:
            return await self.get_relationships_by_entity(owner_scope, book_id, entity_name, limit)
        return await self.get_relationships_by_book(owner_scope, book_id, limit)

    # --- NovelEvent ------------------------------------------------------
    async def save_event(self, owner_scope: str | NovelEvent, event: NovelEvent | None = None) -> NovelEvent:
        if event is None:
            event, owner_scope = owner_scope, LEGACY_SCOPE
        await self._require_book(_scope(owner_scope), event.book_id)
        cursor = await self._db.execute(
            """INSERT INTO novel_events (
                book_id, chapter_id, chapter_num, event_type, description,
                participants, location, importance, related_entities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.book_id,
                event.chapter_id,
                event.chapter_num,
                event.event_type.value,
                event.description,
                json.dumps(event.participants, ensure_ascii=False),
                event.location,
                event.importance,
                json.dumps(event.related_entities, ensure_ascii=False),
            ),
        )
        await self._db.commit()
        event.id = cursor.lastrowid
        return event

    async def save_events_batch(
        self, owner_scope: str | List[NovelEvent], events: List[NovelEvent] | None = None
    ) -> int:
        if events is None:
            events, owner_scope = owner_scope, LEGACY_SCOPE
        for event in events:
            await self.save_event(owner_scope, event)
        return len(events)

    async def get_events(
        self,
        owner_scope: str | int,
        book_id: int | None = None,
        chapter_num: Optional[int] = None,
        event_type: Optional[EventType] = None,
        min_importance: int = 1,
        limit: int = 50,
    ) -> List[NovelEvent]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        conditions = ["n.owner_scope=?", "e.book_id=?", "e.importance>=?"]
        params: list[object] = [scope, book_id, min_importance]
        if chapter_num is not None:
            conditions.append("e.chapter_num=?")
            params.append(chapter_num)
        if event_type is not None:
            conditions.append("e.event_type=?")
            params.append(event_type.value)
        params.append(limit)
        async with self._db.execute(
            f"SELECT e.* FROM novel_events e JOIN novels n ON n.id=e.book_id WHERE {' AND '.join(conditions)} "
            "ORDER BY e.importance DESC LIMIT ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    # --- NovelStateChange ------------------------------------------------
    async def save_state_change(
        self, owner_scope: str | NovelStateChange, sc: NovelStateChange | None = None
    ) -> NovelStateChange:
        if sc is None:
            sc, owner_scope = owner_scope, LEGACY_SCOPE
        await self._require_book(_scope(owner_scope), sc.book_id)
        cursor = await self._db.execute(
            """INSERT INTO novel_state_changes (
                book_id, entity_name, chapter_id, chapter_num, field_name,
                before_value, after_value, trigger_event, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sc.book_id,
                sc.entity_name,
                sc.chapter_id,
                sc.chapter_num,
                sc.field_name.value,
                sc.before_value,
                sc.after_value,
                sc.trigger_event,
                sc.confidence,
            ),
        )
        await self._db.commit()
        sc.id = cursor.lastrowid
        return sc

    async def save_state_changes_batch(
        self, owner_scope: str | List[NovelStateChange], scs: List[NovelStateChange] | None = None
    ) -> int:
        if scs is None:
            scs, owner_scope = owner_scope, LEGACY_SCOPE
        for state_change in scs:
            await self.save_state_change(owner_scope, state_change)
        return len(scs)

    async def get_state_changes(
        self,
        owner_scope: str | int,
        book_id: int | None = None,
        entity_name: Optional[str] = None,
        field_name: Optional[StateField] = None,
        limit: int = 50,
    ) -> List[NovelStateChange]:
        scope, book_id = self._scope_and_id(owner_scope, book_id)
        conditions = ["n.owner_scope=?", "s.book_id=?"]
        params: list[object] = [scope, book_id]
        if entity_name:
            conditions.append("s.entity_name=?")
            params.append(entity_name)
        if field_name:
            conditions.append("s.field_name=?")
            params.append(field_name.value)
        params.append(limit)
        async with self._db.execute(
            f"SELECT s.* FROM novel_state_changes s JOIN novels n ON n.id=s.book_id WHERE {' AND '.join(conditions)} "
            "ORDER BY s.chapter_num DESC LIMIT ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_state_change(row) for row in rows]

    # --- index checkpoints and reading progress -------------------------
    async def save_index_state(self, state: NovelIndexState) -> NovelIndexState:
        await self._require_book(state.owner_scope, state.book_id)
        async with self._db.execute(
            """SELECT id FROM novel_index_states
               WHERE owner_scope=? AND book_id=?
               AND ((chapter_id=? ) OR (chapter_id IS NULL AND ? IS NULL))""",
            (state.owner_scope, state.book_id, state.chapter_id, state.chapter_id),
        ) as cursor:
            existing = await cursor.fetchone()
        values = (
            state.owner_scope,
            state.book_id,
            state.chapter_id,
            state.content_hash,
            state.knowledge_version,
            state.extraction_status,
            state.bm25_status,
            state.vector_status,
            state.embedding_model,
            state.embedding_dimension,
            state.last_success_at,
            state.failure_reason,
        )
        if existing:
            await self._db.execute(
                """UPDATE novel_index_states SET content_hash=?, knowledge_version=?,
                   extraction_status=?, bm25_status=?, vector_status=?, embedding_model=?,
                   embedding_dimension=?, last_success_at=?, failure_reason=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                values[3:] + (existing[0],),
            )
            state_id = existing[0]
        else:
            cursor = await self._db.execute(
                """INSERT INTO novel_index_states (
                   owner_scope, book_id, chapter_id, content_hash, knowledge_version,
                   extraction_status, bm25_status, vector_status, embedding_model,
                   embedding_dimension, last_success_at, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            state_id = cursor.lastrowid
        await self._db.commit()
        state.updated_at = _utcnow_value()
        return state

    async def get_index_state(
        self, owner_scope: str, book_id: int, chapter_id: int | None = None
    ) -> Optional[NovelIndexState]:
        async with self._db.execute(
            """SELECT owner_scope, book_id, chapter_id, content_hash, knowledge_version,
               extraction_status, bm25_status, vector_status, embedding_model,
               embedding_dimension, last_success_at, failure_reason, updated_at
               FROM novel_index_states WHERE owner_scope=? AND book_id=?
               AND ((chapter_id=? ) OR (chapter_id IS NULL AND ? IS NULL))""",
            (_scope(owner_scope), book_id, chapter_id, chapter_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return NovelIndexState(
            owner_scope=row[0],
            book_id=row[1],
            chapter_id=row[2],
            content_hash=row[3],
            knowledge_version=row[4],
            extraction_status=row[5],
            bm25_status=row[6],
            vector_status=row[7],
            embedding_model=row[8],
            embedding_dimension=row[9],
            last_success_at=row[10],
            failure_reason=row[11],
            updated_at=row[12],
        )

    async def save_reading_progress(self, progress: NovelReadingProgress) -> NovelReadingProgress:
        await self._require_book(progress.owner_scope, progress.book_id)
        if not await self._book_exists_for_chapter(progress.owner_scope, progress.chapter_id):
            raise ValueError(f"chapter {progress.chapter_id} does not belong to owner scope {progress.owner_scope!r}")
        progress.percent = max(0.0, min(1.0, float(progress.percent)))
        progress.offset_chars = max(0, int(progress.offset_chars))
        await self._db.execute(
            """INSERT INTO novel_reading_progress (
               owner_scope, book_id, chapter_id, offset_chars, percent, theme,
               background, font_size, line_height, content_width
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_scope, book_id) DO UPDATE SET
               chapter_id=excluded.chapter_id, offset_chars=excluded.offset_chars,
               percent=excluded.percent, theme=excluded.theme,
               background=excluded.background, font_size=excluded.font_size,
               line_height=excluded.line_height, content_width=excluded.content_width,
               updated_at=CURRENT_TIMESTAMP""",
            (
                progress.owner_scope,
                progress.book_id,
                progress.chapter_id,
                progress.offset_chars,
                progress.percent,
                progress.theme,
                progress.background,
                progress.font_size,
                progress.line_height,
                progress.content_width,
            ),
        )
        await self._db.commit()
        progress.updated_at = _utcnow_value()
        return progress

    async def get_reading_progress(
        self, owner_scope: str, book_id: int
    ) -> Optional[NovelReadingProgress]:
        async with self._db.execute(
            """SELECT owner_scope, book_id, chapter_id, offset_chars, percent,
               theme, background, font_size, line_height, content_width, updated_at
               FROM novel_reading_progress WHERE owner_scope=? AND book_id=?""",
            (_scope(owner_scope), book_id),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return NovelReadingProgress(
            owner_scope=row[0],
            book_id=row[1],
            chapter_id=row[2],
            offset_chars=row[3],
            percent=row[4],
            theme=row[5],
            background=row[6],
            font_size=row[7],
            line_height=row[8],
            content_width=row[9],
            updated_at=row[10],
        )

    # --- Row converters --------------------------------------------------
    def _row_to_book(self, row) -> NovelBook:
        owner_scope = row[18] if len(row) >= 19 else LEGACY_SCOPE
        return NovelBook(
            id=row[0],
            book_url=row[1],
            book_name=row[2],
            author=row[3],
            source_name=row[4],
            total_chapters=row[5],
            total_words=row[6],
            status=NovelStatus(row[7]),
            source_type=IngestSource(row[8]),
            ingest_progress=row[9],
            ingest_error_msg=row[10],
            character_count=row[11],
            entity_count=row[12],
            event_count=row[13],
            relationship_count=row[14],
            summary_global=row[15],
            created_at=row[16],
            updated_at=row[17],
            owner_scope=owner_scope,
        )

    def _row_to_chapter(self, row) -> NovelChapter:
        return NovelChapter(
            id=row[0],
            book_id=row[1],
            canonical_type=row[2],
            canonical_num=row[3],
            canonical_full=row[4],
            raw_title=row[5],
            parsed_title_core=row[6],
            raw_chapter_num=row[7],
            source_volume=row[8],
            chapter_num=row[9],
            chapter_title=row[10],
            word_count=row[11],
            raw_text_hash=row[12],
            raw_text=row[13],
            quality_score=row[14],
            summary=row[15],
            key_events=_json_list(row[16]),
            character_appearances=_json_dict(row[17]),
            location_appearances=_json_dict(row[18]),
            mood_tags=_json_list(row[19]),
            arc_tag=row[20],
            arc_summary=row[21],
            created_at=row[22],
        )

    def _row_to_entity(self, row) -> NovelEntity:
        return NovelEntity(
            id=row[0],
            book_id=row[1],
            name=row[2],
            aliases=_json_list(row[3]),
            entity_type=EntityType(row[4]),
            description=row[5],
            first_appearance_ch=row[6],
            last_appearance_ch=row[7],
            appearance_count=row[8],
            importance_score=row[9],
            attributes=_json_dict(row[10]),
            created_at=row[11],
        )

    def _row_to_relationship(self, row) -> NovelRelationship:
        return NovelRelationship(
            id=row[0],
            book_id=row[1],
            source_entity=row[2],
            target_entity=row[3],
            relation_type=RelationType(row[4]),
            description=row[5],
            since_chapter=row[6],
            until_chapter=row[7],
            confidence=row[8],
            created_at=row[9],
        )

    def _row_to_event(self, row) -> NovelEvent:
        return NovelEvent(
            id=row[0],
            book_id=row[1],
            chapter_id=row[2],
            chapter_num=row[3],
            event_type=EventType(row[4]),
            description=row[5],
            participants=_json_list(row[6]),
            location=row[7],
            importance=row[8],
            related_entities=_json_list(row[9]),
            created_at=row[10],
        )

    def _row_to_state_change(self, row) -> NovelStateChange:
        return NovelStateChange(
            id=row[0],
            book_id=row[1],
            entity_name=row[2],
            chapter_id=row[3],
            chapter_num=row[4],
            field_name=StateField(row[5]),
            before_value=row[6],
            after_value=row[7],
            trigger_event=row[8],
            confidence=row[9],
            created_at=row[10],
        )


def _json_list(value) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utcnow_value():
    from datetime import datetime

    return datetime.utcnow()
