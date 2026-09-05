from __future__ import annotations

import copy
import hashlib
import itertools
import json
import re
from dataclasses import replace
from typing import ClassVar

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
    """Deterministic, dependency-free extraction of novel code signals."""

    _cache: ClassVar[dict[tuple[str, str], NovelCodeAnalysisReport]] = {}
    _character_verbs: ClassVar[tuple[str, ...]] = (
        "在", "看见", "抵达", "进入", "离开", "决定", "发现", "说道", "问道",
        "说道", "重逢", "战斗", "死亡", "来到了", "走进",
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
        character_hits: dict[str, list[EvidenceLocation]] = {}
        time_mentions: list[TimeMention] = []
        events: list[EventCandidate] = []
        chapter_names: dict[str, list[str]] = {}

        for chapter in chapters:
            chapter_id = str(chapter["chapter_id"])
            content = str(chapter.get("content", ""))
            names = self._extract_character_hits(chapter_id, content)
            chapter_names[chapter_id] = list(dict.fromkeys(name for name, _ in names))
            for name, evidence in names:
                character_hits.setdefault(name, []).append(evidence)
            for match in self._iter_time_matches(content):
                text = match.group(0)
                anchor_status = "unresolved" if self._is_relative_time(text) else "explicit"
                time_mentions.append(TimeMention(text=text, normalized=text, anchor_status=anchor_status, evidence=[self._evidence(chapter_id, match)]))
            for trigger in self._event_triggers:
                for match in re.finditer(re.escape(trigger), content):
                    evidence = self._evidence(chapter_id, match)
                    events.append(EventCandidate(trigger=trigger, normalized=trigger, confidence=0.9, evidence=[evidence]))

        characters = [
            CharacterCandidate(name=name, normalized=name, count=len(hits), confidence=0.8, evidence=hits)
            for name, hits in sorted(character_hits.items(), key=lambda item: (-len(item[1]), item[0]))
        ]
        cooccurrences = self._cooccurrences(chapter_names, character_hits)
        report = NovelCodeAnalysisReport(
            content_sha256=content_sha256,
            chapters=chapter_models,
            characters=characters,
            cooccurrences=cooccurrences,
            time_mentions=time_mentions,
            events=events,
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
            self._character_patterns = (
                re.compile(rf"(?P<name>[\u4e00-\u9fff]{{2,4}}?)(?=(?:{verbs}))"),
                re.compile(rf"(?P<name>[\u4e00-\u9fff]{{2,4}}?)(?=与|和)|(?:与|和)(?P<name2>[\u4e00-\u9fff]{{2,4}}?)(?=(?:{verbs}|[，。！？]|与|和|$))"),
            )
        blocked = {"他们", "我们", "你们", "自己", "长安", "城门", "翌日", "当晚", "三天后", "半刻后", "在城门", "决定", "进入", "离开"}
        for pattern in self._character_patterns:
            for match in pattern.finditer(content):
                name = match.group("name") or match.group("name2")
                if name in blocked or any(token in name for token in ("时", "后", "前", "天", "刻", "与", "和")):
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
