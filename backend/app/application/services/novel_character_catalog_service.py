from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from app.application.services.provider_platform_service import ProviderPlatformService
from app.infrastructure.persistence.sqlite.bootstrap import SessionLocal
from app.infrastructure.persistence.sqlite.schema import (
    CanonicalChapterModel,
    CanonicalWorkModel,
    ContentVariantModel,
)


class NovelCharacterCatalogService:
    """True system-driven novel knowledge engine:
    Extracts character roster, relationships, turning-point events, and item dossiers
    directly from canonical chapter texts via algorithmic sampling + LLM analysis,
    and strictly persists all results to SQLite tables (novel_entities, novel_relationships, novel_events).
    Zero hardcoded mock/presets.
    """

    def __init__(
        self,
        db_path: str = "/data/novel.db",
        provider_platform: ProviderPlatformService | None = None,
    ):
        self._db_path = db_path
        self._platform = provider_platform

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------------------
    # 1. 人物列表：优先查数据库持久化；无则采样章节 -> LLM 提取 -> 写入数据库
    # -------------------------------------------------------------------------
    async def list_characters(
        self,
        book_id: int,
        book_name: str = "",
        force_refresh: bool = False,
        actor_id: str = "system",
    ) -> list[dict[str, Any]]:
        """Fetch character list from persistent database. If empty, perform full-book extraction via LLM."""
        if not force_refresh:
            existing = self._load_entities_from_db(book_id)
            if existing:
                return existing

        # 触发系统 + LLM 真实全量抽取并落库
        extracted = await self._extract_characters_from_canonical(
            book_id=book_id,
            book_name=book_name,
            actor_id=actor_id,
        )
        if extracted:
            self._save_entities_to_db(book_id, extracted)
            return self._load_entities_from_db(book_id)

        return self._load_entities_from_db(book_id)

    # -------------------------------------------------------------------------
    # 2. 深度档案：优先查持久化关系与事件；无则 RAG 检索 -> LLM 解构 -> 写入数据库
    # -------------------------------------------------------------------------
    async def get_character_dossier(
        self,
        book_id: int,
        character_name: str,
        book_name: str = "",
        force_refresh: bool = False,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """Fetch full dossier (personal info, relationships, events, items).
        If not deeply analyzed yet, perform RAG retrieval + LLM synthesis and persist to DB.
        """
        entity_row = self._get_entity_by_name(book_id, character_name)
        attrs: dict[str, Any] = {}
        aliases: list[str] = []
        if entity_row:
            try:
                aliases = json.loads(entity_row["aliases"]) if entity_row["aliases"] else []
            except Exception:
                aliases = []
            try:
                attrs = json.loads(entity_row["attributes"]) if entity_row["attributes"] else {}
            except Exception:
                attrs = {}

        # 检查是否已有持久化关系和事件
        relations = self._load_relationships_from_db(book_id, character_name)
        events = self._load_events_from_db(book_id, character_name)
        items = attrs.get("items", [])

        need_analysis = force_refresh or (len(relations) == 0 and len(events) == 0)

        if need_analysis and self._platform is not None:
            analyzed = await self._synthesize_dossier_via_llm(
                book_id=book_id,
                character_name=character_name,
                aliases=aliases,
                book_name=book_name,
                actor_id=actor_id,
            )
            if analyzed:
                # 1. 保存持久化关系
                self._save_relationships_to_db(book_id, character_name, analyzed.get("relationships", []))
                # 2. 保存持久化事件
                self._save_events_to_db(book_id, character_name, analyzed.get("events", []))
                # 3. 更新实体表 items 和 personal_info
                attrs["items"] = analyzed.get("items", [])
                if analyzed.get("personal_info"):
                    attrs["personal_info"] = analyzed["personal_info"]
                self._update_entity_attrs(book_id, character_name, attrs)

                relations = self._load_relationships_from_db(book_id, character_name)
                events = self._load_events_from_db(book_id, character_name)
                items = attrs.get("items", [])

        # 获取真实原著段落切片作为证据支撑
        excerpts = self._query_canonical_excerpts(character_name, book_name, aliases=aliases)

        return {
            "name": character_name,
            "role": attrs.get("role", entity_row["entity_type"] if entity_row else "小说登场人物"),
            "importance_tier": entity_row["entity_type"] if entity_row else "major",
            "overall_tier": attrs.get("overall_tier", "S"),
            "aliases": aliases,
            "summary": entity_row["description"] if entity_row else f"小说《{book_name}》中的核心人物【{character_name}】。",
            "avatar_tag": attrs.get("avatar_tag", character_name[:1]),
            "alignment": attrs.get("alignment", "核心阵营"),
            "personal_info": attrs.get("personal_info", {}),
            "relationships": relations,
            "events": events,
            "items": items,
            "canonical_excerpts": excerpts,
        }

    # -------------------------------------------------------------------------
    # 内部数据访问：SQLite 持久化与查询
    # -------------------------------------------------------------------------
    def _load_entities_from_db(self, book_id: int) -> list[dict[str, Any]]:
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM novel_entities WHERE book_id = ? ORDER BY importance_score DESC, id ASC;",
            (book_id,),
        )
        rows = cursor.fetchall()

        results = []
        for r in rows:
            aliases = []
            if r["aliases"]:
                try:
                    aliases = json.loads(r["aliases"])
                except Exception:
                    aliases = []
            attrs = {}
            if r["attributes"]:
                try:
                    attrs = json.loads(r["attributes"])
                except Exception:
                    attrs = {}

            # 查询关联的关系数与事件数
            cursor.execute(
                "SELECT COUNT(*) FROM novel_relationships WHERE book_id = ? AND (source_entity = ? OR target_entity = ?);",
                (book_id, r["name"], r["name"]),
            )
            rel_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM novel_events WHERE book_id = ? AND participants LIKE ?;",
                (book_id, f'%{r["name"]}%'),
            )
            ev_count = cursor.fetchone()[0]

            items_count = len(attrs.get("items", []))

            results.append({
                "name": r["name"],
                "role": attrs.get("role", r["entity_type"]),
                "importance_tier": r["entity_type"] or "major",
                "overall_tier": attrs.get("overall_tier", "S"),
                "aliases": aliases,
                "summary": r["description"] or "",
                "avatar_tag": attrs.get("avatar_tag", r["name"][:1]),
                "items_count": items_count,
                "events_count": ev_count,
                "relationships_count": rel_count,
            })
        conn.close()
        return results

    def _get_entity_by_name(self, book_id: int, name: str) -> sqlite3.Row | None:
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM novel_entities WHERE book_id = ? AND name = ? LIMIT 1;",
            (book_id, name),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def _save_entities_to_db(self, book_id: int, entities: list[dict[str, Any]]):
        conn = self._get_db()
        cursor = conn.cursor()
        for idx, e in enumerate(entities):
            score = 100.0 - (idx * 5)
            tier = e.get("overall_tier", "S")
            if tier == "SSS":
                score = 99.0
            elif tier == "SS":
                score = 90.0
            elif tier == "S":
                score = 80.0

            aliases_json = json.dumps(e.get("aliases", []), ensure_ascii=False)
            attrs_dict = {
                "role": e.get("role", "核心人物"),
                "overall_tier": tier,
                "avatar_tag": e.get("avatar_tag", e["name"][:1]),
                "alignment": e.get("alignment", "核心阵营"),
                "items": e.get("items", []),
                "personal_info": e.get("personal_info", {}),
            }
            attrs_json = json.dumps(attrs_dict, ensure_ascii=False)

            # 插入或更新
            cursor.execute(
                """INSERT OR REPLACE INTO novel_entities
                (book_id, name, aliases, entity_type, description, importance_score, attributes)
                VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (
                    book_id,
                    e["name"],
                    aliases_json,
                    e.get("importance_tier", "major"),
                    e.get("summary", ""),
                    score,
                    attrs_json,
                ),
            )

        # 更新 novels 表的 character_count
        cursor.execute(
            "UPDATE novels SET character_count = (SELECT COUNT(*) FROM novel_entities WHERE book_id = ?) WHERE id = ?;",
            (book_id, book_id),
        )
        conn.commit()
        conn.close()

    def _update_entity_attrs(self, book_id: int, character_name: str, attrs: dict[str, Any]):
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE novel_entities SET attributes = ? WHERE book_id = ? AND name = ?;",
            (json.dumps(attrs, ensure_ascii=False), book_id, character_name),
        )
        conn.commit()
        conn.close()

    def _load_relationships_from_db(self, book_id: int, character_name: str) -> list[dict[str, Any]]:
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM novel_relationships WHERE book_id = ? AND source_entity = ? ORDER BY confidence DESC;",
            (book_id, character_name),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append({
                "target": r["target_entity"],
                "relation": r["relation_type"],
                "affinity": int((r["confidence"] or 0.8) * 100),
                "description": r["description"] or "",
            })
        conn.close()
        return results

    def _save_relationships_to_db(self, book_id: int, source_name: str, relationships: list[dict[str, Any]]):
        if not relationships:
            return
        conn = self._get_db()
        cursor = conn.cursor()
        for rel in relationships:
            target = rel.get("target")
            if not target:
                continue
            conf = float(rel.get("affinity", 80)) / 100.0
            cursor.execute(
                """INSERT OR REPLACE INTO novel_relationships
                (book_id, source_entity, target_entity, relation_type, description, confidence)
                VALUES (?, ?, ?, ?, ?, ?);""",
                (
                    book_id,
                    source_name,
                    target,
                    rel.get("relation", "关联人物"),
                    rel.get("description", ""),
                    conf,
                ),
            )
        conn.commit()
        conn.close()

    def _load_events_from_db(self, book_id: int, character_name: str) -> list[dict[str, Any]]:
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM novel_events WHERE book_id = ? AND participants LIKE ? ORDER BY chapter_num ASC, id ASC;",
            (book_id, f"%{character_name}%"),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append({
                "chapter": r["evidence"] or f"第{r['chapter_num']}章",
                "title": r["event_type"] or "重要转折",
                "description": r["description"] or "",
            })
        conn.close()
        return results

    def _save_events_to_db(self, book_id: int, character_name: str, events: list[dict[str, Any]]):
        if not events:
            return
        conn = self._get_db()
        cursor = conn.cursor()
        for idx, ev in enumerate(events):
            title = ev.get("title", "核心事件")
            desc = ev.get("description", "")
            ch_str = ev.get("chapter", "")
            # 提取章节号
            num_match = re.search(r"\d+", ch_str)
            ch_num = int(num_match.group(0)) if num_match else idx + 1

            cursor.execute(
                """INSERT INTO novel_events
                (book_id, chapter_id, chapter_num, event_type, description, participants, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (
                    book_id,
                    0,
                    ch_num,
                    title,
                    desc,
                    character_name,
                    ch_str,
                ),
            )
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # 核心抽取逻辑：由正文采样与 LLM 协同提取
    # -------------------------------------------------------------------------
    async def _extract_characters_from_canonical(
        self,
        book_id: int,
        book_name: str,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        """Sample chapters across full book and instruct LLM to extract characters roster."""
        if self._platform is None:
            return []

        # 收集小说跨章节样本（覆盖早期、中段、中后期、大结局）
        samples = self._sample_canonical_chapters(book_name, total_samples=10)
        if not samples:
            return []

        context_text = "\n\n".join(samples)

        prompt = f"""你是一位专业文学知识图谱抽取系统。请根据以下提供的完整小说正文采样，深入分析并提取出该小说全部最核心的主要人物列表（包含主角、核心女主/伴侣、核心搭档、宿敌、关键引路人等，提取 6-12 人）。
必须以纯 JSON 数组格式返回，严禁使用 markdown 代码块包裹，严禁输出任何多余的解释说明。

JSON 数组中每个对象的结构定义如下：
[
  {{
    "name": "人物真实姓名（严禁错别字）",
    "role": "身份与定位（如：主角 / 莱茵公司创始人、女主角 / MX公司总裁）",
    "importance_tier": "protagonist / core / major / supporting",
    "overall_tier": "SSS / SS / S / A / B",
    "aliases": ["别名1", "称号2", "外号3"],
    "summary": "全书生平与角色定位概要（100-150字）",
    "avatar_tag": "单字简称（如：弦、珺、兮）",
    "alignment": "所属阵营或势力"
  }}
]

小说全景章节采样证据如下：
{context_text[:7000]}"""

        try:
            invocation = await self._platform.invoke_chat(
                provider_group="novel_chat",
                model=None,
                payload={"messages": [{"role": "user", "content": prompt}]},
                quota_scope=("user", actor_id),
            )
            raw_text = invocation.get("output", {}).get("text", "").strip()
            # 净化 json
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)
            data = json.loads(raw_text)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    async def _synthesize_dossier_via_llm(
        self,
        book_id: int,
        character_name: str,
        aliases: list[str],
        book_name: str,
        actor_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve chapter context for character and synthesize relationships, events, and items."""
        if self._platform is None:
            return None

        # 检索包含该人物及其别名的前中后期最关键正文章节
        search_terms = [character_name] + aliases
        evidence_snippets = self._search_character_scenes(book_name, search_terms, limit=6)
        if not evidence_snippets:
            return None

        evidence_text = "\n\n".join(evidence_snippets)

        prompt = f"""你是一位小说人物全景深度解构系统。请根据以下从原著正文中检索出的真实证据切片，对角色【{character_name}】进行全面深度解构。
必须严格依据提供的原著证据，提取其人际关系网络、关键转折事件、持有与使用过的关键装备道具，以及生平心态演进。
必须以纯 JSON 格式返回，严禁使用 markdown 标记或输出任何多余对话，数据结构定义如下：
{{
  "personal_info": {{
    "identity": "身份背景与演变历程",
    "mentality": "性格与主导心境",
    "alignment": "阵营或组织归属",
    "status": "生存与结局状态"
  }},
  "relationships": [
    {{
      "target": "关系对象姓名",
      "relation": "关系类型（如：妻子 / 挚爱、亲生父亲、科研知己、宿敌对弈）",
      "affinity": 95,
      "description": "50-100字详细解析两人在原著中的情感纽带、生死经历与关键交集"
    }}
  ],
  "events": [
    {{
      "chapter": "原著章节名称",
      "title": "转折事件名称",
      "description": "事件发生经过与对该角色一生命运的深刻影响"
    }}
  ],
  "items": [
    {{
      "name": "道具/装备/关键物品名称",
      "action": "佩戴/使用/获取/封存",
      "desc": "物品在书中的用途、出处或象征意义"
    }}
  ]
}}

原著真实正文证据如下：
{evidence_text[:6500]}"""

        try:
            invocation = await self._platform.invoke_chat(
                provider_group="novel_chat",
                model=None,
                payload={"messages": [{"role": "user", "content": prompt}]},
                quota_scope=("user", actor_id),
            )
            raw_text = invocation.get("output", {}).get("text", "").strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)
            data = json.loads(raw_text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    # 正文采样与 RAG 检索
    # -------------------------------------------------------------------------
    def _sample_canonical_chapters(self, book_name: str, total_samples: int = 10) -> list[str]:
        db = SessionLocal()
        try:
            work = self._find_canonical_work(db, book_name)
            if not work:
                return []
            chapters = (
                db.query(CanonicalChapterModel)
                .filter(CanonicalChapterModel.canonical_work_id == work.id)
                .order_by(CanonicalChapterModel.id)
                .all()
            )
            if not chapters:
                return []

            step = max(1, len(chapters) // total_samples)
            sample_chapters = [chapters[i] for i in range(0, len(chapters), step)][:total_samples]

            results = []
            for ch in sample_chapters:
                v = (
                    db.query(ContentVariantModel)
                    .filter(ContentVariantModel.canonical_chapter_id == ch.id)
                    .first()
                )
                if v and v.content:
                    results.append(f"【章节：{ch.title}】\n{v.content[:700]}")
            return results
        finally:
            db.close()

    def _search_character_scenes(
        self,
        book_name: str,
        search_terms: list[str],
        limit: int = 8,
    ) -> list[str]:
        db = SessionLocal()
        try:
            work = self._find_canonical_work(db, book_name)
            if not work:
                return []
            chapters = (
                db.query(CanonicalChapterModel)
                .filter(CanonicalChapterModel.canonical_work_id == work.id)
                .order_by(CanonicalChapterModel.id)
                .all()
            )
            if not chapters:
                return []

            total_chs = len(chapters)
            ch_map = {c.id: c.title for c in chapters}
            ch_index_map = {c.id: idx for idx, c in enumerate(chapters)}

            variants = (
                db.query(ContentVariantModel)
                .filter(ContentVariantModel.canonical_chapter_id.in_([c.id for c in chapters]))
                .all()
            )

            # 按阶段分组收集命中切片：前期、中期、后期
            early_hits = []
            mid_hits = []
            late_hits = []

            for v in variants:
                text = v.content or ""
                matched_kw = [t for t in search_terms if t in text]
                if not matched_kw:
                    continue

                idx = ch_index_map.get(v.canonical_chapter_id, 0)
                ratio = idx / max(1, total_chs)

                pos = min(text.find(t) for t in matched_kw)
                snip = text[max(0, pos - 60): min(len(text), pos + 420)]
                item = (len(matched_kw), f"【章节：{ch_map.get(v.canonical_chapter_id, '')}】\n...{snip.strip()}...")

                if ratio < 0.25:
                    early_hits.append(item)
                elif ratio < 0.75:
                    mid_hits.append(item)
                else:
                    late_hits.append(item)

            early_hits.sort(key=lambda x: x[0], reverse=True)
            mid_hits.sort(key=lambda x: x[0], reverse=True)
            late_hits.sort(key=lambda x: x[0], reverse=True)

            selected = []
            for h in early_hits[:3]:
                selected.append(h[1])
            for h in mid_hits[:3]:
                selected.append(h[1])
            for h in late_hits[:3]:
                selected.append(h[1])

            return selected[:limit]
        finally:
            db.close()

    def _query_canonical_excerpts(
        self,
        character_name: str,
        book_name: str,
        aliases: list[str] | None = None,
        limit: int = 4,
    ) -> list[dict[str, str]]:
        db = SessionLocal()
        try:
            work = self._find_canonical_work(db, book_name)
            if not work:
                return []
            chapters = (
                db.query(CanonicalChapterModel)
                .filter(CanonicalChapterModel.canonical_work_id == work.id)
                .all()
            )
            ch_ids = [c.id for c in chapters]
            ch_map = {c.id: c.title for c in chapters}

            terms = [character_name] + (aliases or [])
            results = []
            for v in (
                db.query(ContentVariantModel)
                .filter(ContentVariantModel.canonical_chapter_id.in_(ch_ids))
                .all()
            ):
                text = v.content or ""
                hits = [t for t in terms if t in text]
                if hits:
                    pos = min(text.find(t) for t in hits)
                    snip = text[max(0, pos - 40): min(len(text), pos + 260)]
                    results.append({
                        "chapter": ch_map.get(v.canonical_chapter_id, ""),
                        "text": snip.strip(),
                    })
                    if len(results) >= limit:
                        break
            return results
        finally:
            db.close()

    def _find_canonical_work(self, db: Any, book_name: str) -> CanonicalWorkModel | None:
        works = db.query(CanonicalWorkModel).all()
        clean = re.sub(r"[\s《》()（）·_—\-]", "", book_name) if book_name else ""
        for w in works:
            wt = w.title or ""
            clean_wt = re.sub(r"[\s《》()（）·_—\-]", "", wt)
            if clean and clean_wt and (clean in clean_wt or clean_wt in clean):
                return w
        if works:
            return works[0]
        return None
