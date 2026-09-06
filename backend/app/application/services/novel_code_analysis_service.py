from __future__ import annotations

import copy
import hashlib
import itertools
import json
import re
from dataclasses import replace
from typing import Any, ClassVar

from app.domain.entities.novel_code_analysis import (
    ChapterAnalysis,
    CharacterCandidate,
    Cooccurrence,
    EvidenceLocation,
    EventCandidate,
    NovelCodeAnalysisReport,
    TimeMention,
)


class NovelCodeAnalysisService:
    """Deterministic, dependency-free extraction of novel code signals with entity graph and alias clustering."""

    _cache: ClassVar[dict[tuple[str, str], NovelCodeAnalysisReport]] = {}
    _character_verbs: ClassVar[tuple[str, ...]] = (
        "站在", "走在", "坐在", "跑在", "来到了", "走入", "走出", "推门", "看着", "汇报", "倒了",
        "点头", "商讨", "碰面", "倒了", "笑着", "笑了", "说道", "问道", "看见", "抵达", "进入", "离开",
        "决定", "发现", "重逢", "战斗", "死亡", "在", "站", "走", "看", "说", "问",
    )
    _event_triggers: ClassVar[tuple[str, ...]] = (
        "发现", "进入", "离开", "决定", "战斗", "死亡", "重逢",
    )
    _time_lexicon: ClassVar[tuple[str, ...]] = (
        "子时", "丑时", "寅时", "卯时", "辰时", "巳时", "午时", "未时", "申时", "酉时", "戌时", "亥时",
        "当晚", "翌日", "当日", "次日", "今夜", "清晨", "傍晚", "深夜", "黎明",
    )
    _relative_time = re.compile(r"(?<!\d)(?:[一二两三四五六七八九十百千万零〇0-9]+(?:年|月|日|天|小时|时|刻)(?:前|后|之前|之后))(?!\d)")
    _absolute_time = re.compile(r"(?<!\d)(?:\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|\d{4}年|\d{1,2}年|\d{1,2}月|\d{1,2}[日号])(?!\d)")
    _window_size: ClassVar[int] = 80
    _character_patterns: ClassVar[tuple[re.Pattern[str], ...] | None] = None
    _time_pattern: ClassVar[re.Pattern[str] | None] = None

    _blocked_tokens: ClassVar[set[str]] = {
        "他们", "我们", "你们", "自己", "长安", "城门", "翌日", "当晚", "三天后", "半刻后", "在城门",
        "不要", "可是", "虽然", "但是", "只是", "现在", "然而", "如果", "因此", "继续", "发现", "没有", "什么", "怎么",
        "这里", "那里", "这个", "那个", "随后", "接着", "突然", "此时", "当时", "旁边", "四周", "身后", "面前", "哪怕",
        "因为", "所以", "不过", "只见", "为了", "似乎", "好像", "仿佛", "一下", "已经", "正在", "开始", "最后", "同时",
        "决定", "进入", "离开", "战斗", "死亡", "重逢", "一位", "一个", "只见", "这时", "这时他", "可是现", "在他必须",
    }

    def analyze(self, work_id: str, chapters: list[dict]) -> NovelCodeAnalysisReport:
        content_sha256 = self._content_hash(chapters)
        key = (work_id, content_sha256)
        cached = self._cache.get(key)
        if cached is not None:
            return replace(copy.deepcopy(cached), cache_hit=True)

        chapter_models = [
            ChapterAnalysis(
                chapter_id=str(chapter["chapter_id"]),
                chapter_index=int(chapter["chapter_index"]),
                title=str(chapter.get("title", "")),
                content_sha256=hashlib.sha256(str(chapter.get("content", "")).encode("utf-8")).hexdigest(),
            )
            for chapter in chapters
        ]
        raw_character_hits: dict[str, list[EvidenceLocation]] = {}
        time_mentions: list[TimeMention] = []
        events: list[EventCandidate] = []
        chapter_names: dict[str, list[str]] = {}

        for chapter in chapters:
            chapter_id = str(chapter["chapter_id"])
            content = str(chapter.get("content", ""))
            names = self._extract_character_hits(chapter_id, content)
            chapter_names[chapter_id] = list(dict.fromkeys(name for name, _ in names))
            for name, evidence in names:
                raw_character_hits.setdefault(name, []).append(evidence)
            for match in self._iter_time_matches(content):
                text = match.group(0)
                anchor_status = "unresolved" if self._is_relative_time(text) else "explicit"
                time_mentions.append(TimeMention(text=text, normalized=text, anchor_status=anchor_status, evidence=[self._evidence(chapter_id, match)]))
            for trigger in self._event_triggers:
                for match in re.finditer(re.escape(trigger), content):
                    evidence = self._evidence(chapter_id, match)
                    events.append(EventCandidate(trigger=trigger, normalized=trigger, confidence=0.9, evidence=[evidence]))

        characters, character_graph, merged_hits = self._cluster_and_rank_characters(raw_character_hits, chapter_names)
        cooccurrences = self._cooccurrences(chapter_names, merged_hits)

        report = NovelCodeAnalysisReport(
            content_sha256=content_sha256,
            chapters=chapter_models,
            characters=characters,
            cooccurrences=cooccurrences,
            time_mentions=time_mentions,
            events=events,
            character_graph=character_graph,
            warnings=[],
            cache_hit=False,
        )
        self._cache[key] = copy.deepcopy(report)
        return copy.deepcopy(report)

    @staticmethod
    def _content_hash(chapters: list[dict]) -> str:
        payload = [
            {
                "chapter_id": str(chapter["chapter_id"]),
                "chapter_index": int(chapter["chapter_index"]),
                "title": str(chapter.get("title", "")),
                "content": str(chapter.get("content", "")),
            }
            for chapter in chapters
        ]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _extract_character_hits(self, chapter_id: str, content: str) -> list[tuple[str, EvidenceLocation]]:
        hits: list[tuple[str, EvidenceLocation]] = []
        if self._character_patterns is None:
            verbs = "|".join(sorted((re.escape(v) for v in self._character_verbs), key=len, reverse=True))
            punct = r"[\s\n，。！？；：、“”‘’]"
            boundary = r"[\s\n，。！？；：、“”‘’向往从与和道说看走在笑]"
            self._character_patterns = (
                re.compile(rf"(?:^|{punct})(?P<name>[\u4e00-\u9fff]{{2,3}}?)(?=(?:{verbs}))"),
                re.compile(rf"(?:^|{punct})(?P<name>[\u4e00-\u9fff]{{2,3}}?)(?=与|和)|(?:与|和)(?P<name2>[\u4e00-\u9fff]{{2,3}}?)(?=(?:{verbs}|{punct}|与|和|$))"),
                re.compile(rf"(?:^|{punct})(?P<name>(?:老|小|阿)[\u4e00-\u9fff]{{1,2}}?)(?={boundary}|(?:{verbs})|$)"),
                re.compile(rf"(?:^|{punct})(?P<name>[\u4e00-\u9fff]{{1,2}}?(?:哥|姐|总|叔|伯|老|师|队长|组长))(?={boundary}|(?:{verbs})|$)"),
            )

        for pattern in self._character_patterns:
            for match in pattern.finditer(content):
                name = match.group("name") or match.group("name2")
                if not name:
                    continue
                name = name.strip()
                if name in self._blocked_tokens or any(token in name for token in ("时", "后", "前", "天", "刻", "与", "和")):
                    continue
                if any(noise in name for noise in ("不要", "可是", "虽然", "但是", "然而", "如果", "因此", "继续", "离开", "进入", "决定", "发现")):
                    continue
                if any(name.endswith(end) for end in ("着", "了", "过", "的", "得", "地", "去", "来", "一", "二", "声", "步")):
                    continue
                if len(set(name)) == 1 or any(name.count(char) > 1 for char in name[:1]):
                    continue
                if any(trigger in name for trigger in self._event_triggers):
                    continue

                group_name = "name" if match.group("name") else "name2"
                start, end = match.span(group_name)
                evidence = EvidenceLocation(chapter_id=chapter_id, start_offset=start, end_offset=end, text=name)
                hits.append((name, evidence))

        unique: dict[tuple[str, int, int], tuple[str, EvidenceLocation]] = {}
        for name, evidence in hits:
            unique[(name, evidence.start_offset, evidence.end_offset)] = (name, evidence)
        return list(unique.values())

    def _cluster_and_rank_characters(
        self,
        raw_hits: dict[str, list[EvidenceLocation]],
        chapter_names: dict[str, list[str]],
    ) -> tuple[list[CharacterCandidate], dict[str, Any], dict[str, list[EvidenceLocation]]]:
        """Performs alias clustering (e.g. 小林, 弦哥 -> 林弦) and degree centrality ranking."""
        formal_candidates = sorted(
            [name for name in raw_hits.keys() if len(name) >= 2 and not any(name.startswith(p) for p in ("老", "小", "阿")) and not any(name.endswith(s) for s in ("哥", "姐", "总", "叔", "组长", "队长"))],
            key=lambda x: len(raw_hits[x]),
            reverse=True,
        )

        alias_map: dict[str, str] = {}  # alias -> canonical
        aliases_of: dict[str, list[str]] = {name: [] for name in raw_hits.keys()}

        for name in list(raw_hits.keys()):
            if name in formal_candidates:
                continue
            # Extract stem
            stem = name
            for prefix in ("老", "小", "阿", "大"):
                if name.startswith(prefix) and len(name) > 1:
                    stem = name[len(prefix):]
                    break
            for suffix in ("哥", "姐", "总", "叔", "伯", "老", "师", "队长", "组长"):
                if stem.endswith(suffix) and len(stem) > 1:
                    stem = stem[:-len(suffix)]
                    break

            # Find best formal candidate sharing characters with stem
            best_canonical = None
            for formal in formal_candidates:
                if any(char in formal for char in stem) or stem in formal:
                    best_canonical = formal
                    break

            if best_canonical and best_canonical != name:
                alias_map[name] = best_canonical
                aliases_of.setdefault(best_canonical, []).append(name)

        # Merge hits into canonical candidates
        merged_hits: dict[str, list[EvidenceLocation]] = {}
        for name, evidences in raw_hits.items():
            canonical = alias_map.get(name, name)
            merged_hits.setdefault(canonical, []).extend(evidences)

        # Build co-occurrence graph to determine degree centrality
        character_connections: dict[str, set[str]] = {name: set() for name in merged_hits.keys()}
        for names in chapter_names.values():
            resolved = {alias_map.get(n, n) for n in names if alias_map.get(n, n) in merged_hits}
            for left, right in itertools.combinations(resolved, 2):
                character_connections[left].add(right)
                character_connections[right].add(left)

        # Calculate centrality & tier
        candidates: list[CharacterCandidate] = []
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        total_characters = len(merged_hits)
        sorted_names = sorted(merged_hits.keys(), key=lambda k: (-len(merged_hits[k]), -len(character_connections.get(k, set()))))

        for idx, name in enumerate(sorted_names):
            evidences = merged_hits[name]
            conn = character_connections.get(name, set())
            centrality = round(len(conn) + (len(evidences) * 0.1), 2)
            
            # Importance tier classification
            if idx == 0 and len(evidences) >= 2:
                tier = "protagonist"
            elif len(evidences) >= 3 or len(conn) >= 2:
                tier = "major"
            else:
                tier = "minor"

            char_aliases = sorted(set(aliases_of.get(name, [])))
            candidates.append(
                CharacterCandidate(
                    name=name,
                    normalized=name,
                    count=len(evidences),
                    confidence=0.85 if tier in ("protagonist", "major") else 0.7,
                    evidence=evidences,
                    aliases=char_aliases,
                    importance_tier=tier,
                    centrality=centrality,
                )
            )
            nodes.append({"id": name, "tier": tier, "count": len(evidences), "aliases": char_aliases, "centrality": centrality})

        for (u, neighbors) in character_connections.items():
            for v in neighbors:
                if u < v:
                    edges.append({"source": u, "target": v})

        character_graph = {"nodes": nodes, "edges": edges}
        return candidates, character_graph, merged_hits

    def _iter_time_matches(self, content: str):
        if self._time_pattern is None:
            self._time_pattern = re.compile(
                "|".join(
                    [self._relative_time.pattern, self._absolute_time.pattern]
                    + [re.escape(value) for value in sorted(self._time_lexicon, key=len, reverse=True)]
                )
            )
        return self._time_pattern.finditer(content)

    def _is_relative_time(self, text: str) -> bool:
        return bool(self._relative_time.fullmatch(text)) or text in {"当晚", "翌日", "当日", "次日", "今夜"}

    @staticmethod
    def _evidence(chapter_id: str, match: re.Match[str]) -> EvidenceLocation:
        return EvidenceLocation(chapter_id=chapter_id, start_offset=match.start(), end_offset=match.end(), text=match.group(0))

    def _cooccurrences(self, chapter_names: dict[str, list[str]], character_hits: dict[str, list[EvidenceLocation]]) -> list[Cooccurrence]:
        del chapter_names
        pair_data: dict[tuple[str, str], tuple[int, list[EvidenceLocation]]] = {}
        by_chapter: dict[str, list[tuple[str, EvidenceLocation]]] = {}
        for name, evidences in character_hits.items():
            for evidence in evidences:
                by_chapter.setdefault(evidence.chapter_id, []).append((name, evidence))
        for chapter_id, hits in by_chapter.items():
            windows: dict[int, list[tuple[str, EvidenceLocation]]] = {}
            for name, evidence in hits:
                windows.setdefault(evidence.start_offset // self._window_size, []).append((name, evidence))
            for window_hits in windows.values():
                names = sorted({name for name, _ in window_hits})
                for left, right in itertools.combinations(names, 2):
                    key = (left, right)
                    count, evidence = pair_data.get(key, (0, []))
                    pair_data[key] = (count + 1, evidence + [item for _, item in window_hits])
        return [
            Cooccurrence(left=left, right=right, count=count, evidence=evidence)
            for (left, right), (count, evidence) in sorted(pair_data.items())
        ]
