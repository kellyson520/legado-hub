"""
NovelRepository 的 SQLite 实现

- JSON 字段用 TEXT 存储，通过 json.dumps/json.loads 转换
- 支持 UPSERT（ON CONFLICT）用于 book_url 和 entity name 的唯一约束
- 所有方法为 async，使用 aiosqlite
"""

import json
from typing import List, Optional

from app.domain.repositories.novel_repo import NovelRepository
from app.domain.entities.novel import (
    NovelBook, NovelChapter, NovelChapterMirror, ChapterFingerprint,
    NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    NovelStatus, EntityType, EventType, StateField, RelationType,
    NovelSourceMirror, IngestSource,
)


class SqliteNovelRepository(NovelRepository):
    def __init__(self, db):
        self._db = db

    # --- NovelBook ---
    async def save_book(self, book: NovelBook) -> NovelBook:
        cursor = await self._db.execute(
            """INSERT INTO novels (book_url, book_name, author, source_name, total_chapters, total_words,
                status, source_type, ingest_progress, ingest_error_msg, summary_global)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_url) DO UPDATE SET
                book_name=excluded.book_name, author=excluded.author,
                source_name=excluded.source_name, total_chapters=excluded.total_chapters,
                total_words=excluded.total_words, status=excluded.status,
                source_type=excluded.source_type, ingest_progress=excluded.ingest_progress,
                ingest_error_msg=excluded.ingest_error_msg, summary_global=excluded.summary_global,
                updated_at=CURRENT_TIMESTAMP""",
            (book.book_url, book.book_name, book.author, book.source_name,
             book.total_chapters, book.total_words, book.status.value, book.source_type.value,
             book.ingest_progress, book.ingest_error_msg, book.summary_global)
        )
        await self._db.commit()
        book.id = cursor.lastrowid
        return book

    async def get_book_by_id(self, book_id: int) -> Optional[NovelBook]:
        async with self._db.execute("SELECT * FROM novels WHERE id=?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_book(row)
        return None

    async def get_book(self, book_id: int) -> Optional[NovelBook]:
        return await self.get_book_by_id(book_id)

    async def get_book_by_url(self, book_url: str) -> Optional[NovelBook]:
        async with self._db.execute("SELECT * FROM novels WHERE book_url=?", (book_url,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_book(row)
        return None

    async def list_books(self, status: Optional[NovelStatus] = None, limit: int = 20, offset: int = 0) -> List[NovelBook]:
        if status:
            async with self._db.execute("SELECT * FROM novels WHERE status=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                                        (status.value, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute("SELECT * FROM novels ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                                        (limit, offset)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_book(r) for r in rows]

    async def count_books(self, status: Optional[NovelStatus] = None) -> int:
        if status:
            async with self._db.execute("SELECT COUNT(*) FROM novels WHERE status=?", (status.value,)) as cursor:
                row = await cursor.fetchone()
                return row[0]
        async with self._db.execute("SELECT COUNT(*) FROM novels") as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def update_book_status(self, book_id: int, status: NovelStatus, progress: Optional[float] = None, error_msg: Optional[str] = None) -> bool:
        fields = ["status=?"]
        params = [status.value]
        if progress is not None:
            fields.append("ingest_progress=?")
            params.append(progress)
        if error_msg is not None:
            fields.append("ingest_error_msg=?")
            params.append(error_msg)
        params.append(book_id)
        await self._db.execute(f"UPDATE novels SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", params)
        await self._db.commit()
        return True

    async def update_book_summary(self, book_id: int, summary: str) -> bool:
        await self._db.execute("UPDATE novels SET summary_global=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                               (summary, book_id))
        await self._db.commit()
        return True

    async def delete_book(self, book_id: int) -> bool:
        await self._db.execute("DELETE FROM novels WHERE id=?", (book_id,))
        await self._db.commit()
        return True

    # --- NovelChapter ---
    async def save_chapter(self, chapter: NovelChapter) -> NovelChapter:
        cursor = await self._db.execute(
            """INSERT INTO novel_chapters (book_id, canonical_type, canonical_num, canonical_full,
                raw_title, parsed_title_core, raw_chapter_num, source_volume, chapter_num, chapter_title,
                word_count, raw_text_hash, raw_text, quality_score, summary, key_events, character_appearances,
                location_appearances, mood_tags, arc_tag, arc_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chapter.book_id, chapter.canonical_type, chapter.canonical_num, chapter.canonical_full,
             chapter.raw_title, chapter.parsed_title_core, chapter.raw_chapter_num, chapter.source_volume,
             chapter.chapter_num, chapter.chapter_title, chapter.word_count, chapter.raw_text_hash,
             chapter.raw_text, chapter.quality_score, chapter.summary,
             json.dumps(chapter.key_events, ensure_ascii=False),
             json.dumps(chapter.character_appearances, ensure_ascii=False),
             json.dumps(chapter.location_appearances, ensure_ascii=False),
             json.dumps(chapter.mood_tags, ensure_ascii=False),
             chapter.arc_tag, chapter.arc_summary)
        )
        await self._db.commit()
        chapter.id = cursor.lastrowid
        return chapter

    async def save_chapters_batch(self, chapters: List[NovelChapter]) -> int:
        for ch in chapters:
            await self.save_chapter(ch)
        return len(chapters)

    async def get_chapter_by_id(self, chapter_id: int) -> Optional[NovelChapter]:
        async with self._db.execute("SELECT * FROM novel_chapters WHERE id=?", (chapter_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_chapter(row)
        return None

    async def get_chapter(self, chapter_id: int) -> Optional[NovelChapter]:
        return await self.get_chapter_by_id(chapter_id)

    async def get_chapters_by_book(self, book_id: int, start_num: int = 1, end_num: Optional[int] = None, limit: int = 100, offset: int = 0) -> List[NovelChapter]:
        conditions = ["book_id=?", "canonical_num >= ?"]
        params = [book_id, start_num]
        if end_num:
            conditions.append("canonical_num <= ?")
            params.append(end_num)
        params.extend([limit, offset])
        query = f"SELECT * FROM novel_chapters WHERE {' AND '.join(conditions)} ORDER BY canonical_num LIMIT ? OFFSET ?"
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_chapter(r) for r in rows]

    async def count_chapters(self, book_id: int) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM novel_chapters WHERE book_id=?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def update_chapter_summary(self, chapter_id: int, summary: str, key_events: List[str]) -> bool:
        await self._db.execute(
            "UPDATE novel_chapters SET summary=?, key_events=? WHERE id=?",
            (summary, json.dumps(key_events, ensure_ascii=False), chapter_id))
        await self._db.commit()
        return True

    async def update_chapter_content(self, chapter_id: int, content: str, quality_score: Optional[float] = None) -> bool:
        fields = ["raw_text=?", "word_count=?"]
        params = [content, len(content)]
        if quality_score is not None:
            fields.append("quality_score=?")
            params.append(quality_score)
        params.append(chapter_id)
        await self._db.execute(f"UPDATE novel_chapters SET {', '.join(fields)} WHERE id=?", params)
        await self._db.commit()
        return True

    # --- NovelEntity ---
    async def save_entity(self, entity: NovelEntity) -> NovelEntity:
        cursor = await self._db.execute(
            """INSERT INTO novel_entities (book_id, name, aliases, entity_type, description,
                first_appearance_ch, last_appearance_ch, appearance_count, importance_score, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, name) DO UPDATE SET
                aliases=excluded.aliases, entity_type=excluded.entity_type,
                description=excluded.description, first_appearance_ch=excluded.first_appearance_ch,
                last_appearance_ch=excluded.last_appearance_ch, appearance_count=excluded.appearance_count,
                importance_score=excluded.importance_score, attributes=excluded.attributes""",
            (entity.book_id, entity.name, json.dumps(entity.aliases, ensure_ascii=False),
             entity.entity_type.value, entity.description, entity.first_appearance_ch,
             entity.last_appearance_ch, entity.appearance_count, entity.importance_score,
             json.dumps(entity.attributes, ensure_ascii=False))
        )
        await self._db.commit()
        if entity.id == 0:
            entity.id = cursor.lastrowid
        return entity

    async def save_entities_batch(self, entities: List[NovelEntity]) -> int:
        for e in entities:
            await self.save_entity(e)
        return len(entities)

    async def get_entity_by_id(self, entity_id: int) -> Optional[NovelEntity]:
        async with self._db.execute("SELECT * FROM novel_entities WHERE id=?", (entity_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entity(row)
        return None

    async def get_entity(self, entity_id: int) -> Optional[NovelEntity]:
        return await self.get_entity_by_id(entity_id)

    async def get_entity_by_name(self, book_id: int, name: str) -> Optional[NovelEntity]:
        async with self._db.execute("SELECT * FROM novel_entities WHERE book_id=? AND name=?", (book_id, name)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entity(row)
        return None

    async def list_entities(self, book_id: int, entity_type: Optional[EntityType] = None, limit: int = 50, offset: int = 0) -> List[NovelEntity]:
        if entity_type:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND entity_type=? ORDER BY importance_score DESC LIMIT ? OFFSET ?",
                (book_id, entity_type.value, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? ORDER BY importance_score DESC LIMIT ? OFFSET ?",
                (book_id, limit, offset)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_entity(r) for r in rows]

    async def count_entities(self, book_id: int, entity_type: Optional[EntityType] = None) -> int:
        if entity_type:
            async with self._db.execute(
                "SELECT COUNT(*) FROM novel_entities WHERE book_id=? AND entity_type=?",
                (book_id, entity_type.value)) as cursor:
                row = await cursor.fetchone()
                return row[0]
        async with self._db.execute("SELECT COUNT(*) FROM novel_entities WHERE book_id=?", (book_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def get_entity_names_by_book(self, book_id: int) -> List[str]:
        async with self._db.execute("SELECT name FROM novel_entities WHERE book_id=? ORDER BY importance_score DESC", (book_id,)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def search_entities(self, book_id: int, keyword: str, entity_type: Optional[EntityType] = None, limit: int = 20) -> List[NovelEntity]:
        pattern = f"%{keyword}%"
        if entity_type:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND entity_type=? AND (name LIKE ? OR description LIKE ?) LIMIT ?",
                (book_id, entity_type.value, pattern, pattern, limit)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute(
                "SELECT * FROM novel_entities WHERE book_id=? AND (name LIKE ? OR description LIKE ?) LIMIT ?",
                (book_id, pattern, pattern, limit)) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_entity(r) for r in rows]

    # --- NovelRelationship ---
    async def save_relationship(self, rel: NovelRelationship) -> NovelRelationship:
        cursor = await self._db.execute(
            """INSERT INTO novel_relationships (book_id, source_entity, target_entity, relation_type,
                description, since_chapter, until_chapter, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel.book_id, rel.source_entity, rel.target_entity, rel.relation_type.value,
             rel.description, rel.since_chapter, rel.until_chapter, rel.confidence)
        )
        await self._db.commit()
        rel.id = cursor.lastrowid
        return rel

    async def save_relationships_batch(self, rels: List[NovelRelationship]) -> int:
        for r in rels:
            await self.save_relationship(r)
        return len(rels)

    async def get_relationships_by_book(self, book_id: int, limit: int = 50) -> List[NovelRelationship]:
        async with self._db.execute(
            "SELECT * FROM novel_relationships WHERE book_id=? LIMIT ?",
            (book_id, limit)) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_relationship(r) for r in rows]

    async def get_relationships_by_entity(self, book_id: int, entity_name: str, limit: int = 50) -> List[NovelRelationship]:
        async with self._db.execute(
            """SELECT * FROM novel_relationships WHERE book_id=? 
                AND (source_entity=? OR target_entity=?) LIMIT ?""",
            (book_id, entity_name, entity_name, limit)) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_relationship(r) for r in rows]

    async def get_relationships(self, book_id: int, entity_name: Optional[str] = None, limit: int = 50) -> List[NovelRelationship]:
        if entity_name:
            return await self.get_relationships_by_entity(book_id, entity_name, limit)
        return await self.get_relationships_by_book(book_id, limit)

    # --- NovelEvent ---
    async def save_event(self, event: NovelEvent) -> NovelEvent:
        cursor = await self._db.execute(
            """INSERT INTO novel_events (book_id, chapter_id, chapter_num, event_type, description,
                participants, location, importance, related_entities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.book_id, event.chapter_id, event.chapter_num, event.event_type.value,
             event.description, json.dumps(event.participants, ensure_ascii=False),
             event.location, event.importance,
             json.dumps(event.related_entities, ensure_ascii=False))
        )
        await self._db.commit()
        event.id = cursor.lastrowid
        return event

    async def save_events_batch(self, events: List[NovelEvent]) -> int:
        for e in events:
            await self.save_event(e)
        return len(events)

    async def get_events(self, book_id: int, chapter_num: Optional[int] = None, event_type: Optional[EventType] = None, min_importance: int = 1, limit: int = 50) -> List[NovelEvent]:
        conditions = ["book_id=?"]
        params = [book_id]
        if chapter_num is not None:
            conditions.append("chapter_num=?")
            params.append(chapter_num)
        if event_type is not None:
            conditions.append("event_type=?")
            params.append(event_type.value)
        conditions.append("importance>=?")
        params.append(min_importance)
        params.append(limit)

        query = f"SELECT * FROM novel_events WHERE {' AND '.join(conditions)} ORDER BY importance DESC LIMIT ?"
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    # --- NovelStateChange ---
    async def save_state_change(self, sc: NovelStateChange) -> NovelStateChange:
        cursor = await self._db.execute(
            """INSERT INTO novel_state_changes (book_id, entity_name, chapter_id, chapter_num,
                field_name, before_value, after_value, trigger_event, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sc.book_id, sc.entity_name, sc.chapter_id, sc.chapter_num,
             sc.field_name.value, sc.before_value, sc.after_value, sc.trigger_event, sc.confidence)
        )
        await self._db.commit()
        sc.id = cursor.lastrowid
        return sc

    async def save_state_changes_batch(self, scs: List[NovelStateChange]) -> int:
        for sc in scs:
            await self.save_state_change(sc)
        return len(scs)

    async def get_state_changes(self, book_id: int, entity_name: Optional[str] = None, field_name: Optional[StateField] = None, limit: int = 50) -> List[NovelStateChange]:
        conditions = ["book_id=?"]
        params = [book_id]
        if entity_name:
            conditions.append("entity_name=?")
            params.append(entity_name)
        if field_name:
            conditions.append("field_name=?")
            params.append(field_name.value)
        params.append(limit)

        query = f"SELECT * FROM novel_state_changes WHERE {' AND '.join(conditions)} ORDER BY chapter_num DESC LIMIT ?"
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_state_change(r) for r in rows]

    # --- Row converters ---
    def _row_to_book(self, row) -> NovelBook:
        return NovelBook(
            id=row[0], book_url=row[1], book_name=row[2], author=row[3],
            source_name=row[4], total_chapters=row[5], total_words=row[6],
            status=NovelStatus(row[7]), source_type=IngestSource(row[8]),
            ingest_progress=row[9], ingest_error_msg=row[10],
            character_count=row[11], entity_count=row[12], event_count=row[13],
            relationship_count=row[14], summary_global=row[15],
            created_at=row[16], updated_at=row[17]
        )

    def _row_to_chapter(self, row) -> NovelChapter:
        cols = len(row)
        if cols >= 23:
            return NovelChapter(
                id=row[0], book_id=row[1], canonical_type=row[2], canonical_num=row[3],
                canonical_full=row[4], raw_title=row[5], parsed_title_core=row[6],
                raw_chapter_num=row[7], source_volume=row[8], chapter_num=row[9],
                chapter_title=row[10], word_count=row[11], raw_text_hash=row[12],
                raw_text=row[13], quality_score=row[14], summary=row[15],
                key_events=json.loads(row[16]),
                character_appearances=json.loads(row[17]),
                location_appearances=json.loads(row[18]),
                mood_tags=json.loads(row[19]), arc_tag=row[20], arc_summary=row[21],
                created_at=row[22]
            )
        else:
            return NovelChapter(
                id=row[0], book_id=row[1], canonical_type=row[2], canonical_num=row[3],
                canonical_full=row[4], raw_title=row[5], parsed_title_core=row[6],
                raw_chapter_num=row[7], source_volume=row[8], chapter_num=row[9],
                chapter_title=row[10], word_count=row[11], raw_text_hash=row[12],
                summary=row[13], key_events=json.loads(row[14]),
                character_appearances=json.loads(row[15]),
                location_appearances=json.loads(row[16]),
                mood_tags=json.loads(row[17]), arc_tag=row[18], arc_summary=row[19],
                created_at=row[20]
            )

    def _row_to_entity(self, row) -> NovelEntity:
        return NovelEntity(
            id=row[0], book_id=row[1], name=row[2], aliases=json.loads(row[3]),
            entity_type=EntityType(row[4]), description=row[5],
            first_appearance_ch=row[6], last_appearance_ch=row[7],
            appearance_count=row[8], importance_score=row[9],
            attributes=json.loads(row[10]), created_at=row[11]
        )

    def _row_to_relationship(self, row) -> NovelRelationship:
        return NovelRelationship(
            id=row[0], book_id=row[1], source_entity=row[2], target_entity=row[3],
            relation_type=RelationType(row[4]), description=row[5],
            since_chapter=row[6], until_chapter=row[7], confidence=row[8],
            created_at=row[9]
        )

    def _row_to_event(self, row) -> NovelEvent:
        return NovelEvent(
            id=row[0], book_id=row[1], chapter_id=row[2], chapter_num=row[3],
            event_type=EventType(row[4]), description=row[5],
            participants=json.loads(row[6]), location=row[7],
            importance=row[8], related_entities=json.loads(row[9]),
            created_at=row[10]
        )

    def _row_to_state_change(self, row) -> NovelStateChange:
        return NovelStateChange(
            id=row[0], book_id=row[1], entity_name=row[2], chapter_id=row[3],
            chapter_num=row[4], field_name=StateField(row[5]),
            before_value=row[6], after_value=row[7], trigger_event=row[8],
            confidence=row[9], created_at=row[10]
        )
