"""Evidence-first deterministic candidate extraction for novel chapters."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any, Iterable

from app.domain.entities.novel import EntityType, NovelEntity, NovelRelationship, RelationType


@dataclass(frozen=True)
class CandidateEvidence:
    chapter_id: int
    chapter_num: int
    start_offset: int
    end_offset: int
    text: str
    features: tuple[str, ...] = ()


@dataclass
class LocalCandidate:
    name: str
    entity_type: EntityType
    score: float
    mentions: int
    evidence: list[CandidateEvidence]
    aliases: list[str] = field(default_factory=list)
    subtype: str = ""
    status: str = "confirmed"


class CandidateExtractor:
    """Extract bounded, evidence-backed candidates without an LLM."""

    COMMON_SURNAMES = set(
        "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗方俞任袁柳鲍史唐薛雷贺倪汤滕殷罗毕郝安常乐傅齐康伍余顾孟平黄穆萧尹姚邵汪毛狄米明成戴宋庞熊纪舒屈项祝董梁杜阮蓝季麻贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍崔邓曾卢丁叶强",
    )
    PERSON_CONTEXT = {
        "说", "道", "问", "答", "看", "望", "走", "站", "坐", "蹲", "穿", "拿",
        "握", "挥", "笑", "哭", "怒", "惊", "叹", "喊", "叫", "赶", "冲", "挡",
        "点头", "摇头", "眼中", "脸上", "心中", "身后", "面前", "身上", "与", "和",
        "很", "便", "是", "在", "将", "把", "向", "对", "并", "说到", "问道",
    }
    PERSON_STOPWORDS = {
        "之后", "之前", "时候", "地方", "东西", "事情", "世界", "开始", "结束", "已经",
        "正在", "突然", "慢慢", "渐渐", "有些", "很多", "周围", "其中", "这个", "那个",
        "自己", "因为", "所以", "无法", "可能", "强烈", "周边", "附近", "毕竟", "麻烦",
        "成长", "安全", "危险", "平地", "平常", "平日里", "方才", "何处", "无异", "明天",
        "高呼", "高深", "凌乱", "水灵", "清丽", "屈辱", "高潮",
        "任由", "常识", "强制",
    }
    TITLE_WORDS = {
        "姑娘", "公子", "小姐", "少爷", "师兄", "师姐", "师弟", "师妹", "殿下", "前辈",
        "大人", "掌门", "长老", "夫人", "先生", "老祖", "道友", "将军", "圣女", "圣子",
    }
    GENERIC_PERSON_TERMS = TITLE_WORDS | {
        "郎君", "孩子", "儿子", "女儿", "子嗣", "少年", "少女", "女子", "男人", "女人",
        "女帝", "圣上", "太子", "世子", "王上", "小娘子", "胖子", "刺客", "侍女", "主人",
    }
    NAME_PREFIXES = set("与和及向对把将为让在从由给被同陪随替见看望")
    NAME_TAIL_STOPWORDS = set("很便是算赶冲问说道看望正在已经的了着与和在向其他她并")
    NAME_AFTER_PARTICLES = set("也的了着就便是在向和与及")
    ADDRESS_SUFFIXES = set("兄姐哥妹弟叔姨爷")
    TITLE_PHRASES = {
        "姑娘", "小姐", "公子", "元帅", "神女", "仙子", "师兄", "师姐", "师弟", "师妹",
        "殿下", "前辈", "大人", "掌门", "长老", "夫人", "先生", "老祖", "道友", "将军",
        "圣女", "圣子",
    }
    ITEM_ACTIONS = {
        "取出", "拿出", "掏出", "获得", "得到", "捡到", "握住", "拿着", "佩戴", "戴上",
        "使用", "祭出", "炼制", "赠予", "赠给", "交给", "收入", "收起", "摧毁", "损坏",
        "修复", "激活", "催动", "召出",
    }
    ITEM_SUFFIXES = ("剑", "刀", "枪", "戟", "弓", "箭", "甲", "盾", "戒", "环", "玉", "佩", "符", "令", "珠", "丹", "炉", "鼎", "镜", "图", "书", "卷", "印", "塔", "钟", "伞")
    LOCATION_SUFFIXES = ("山", "峰", "谷", "洞", "城", "镇", "村", "宫", "府", "岛", "河", "湖", "桥", "街", "园", "阁", "楼", "殿")
    FACTION_SUFFIXES = ("宗", "派", "门", "教", "帮", "会", "盟", "军", "团", "营", "寨", "阁", "殿", "宫", "府", "院")
    RELATION_CUES = {
        RelationType.ALLY: ("并肩作战", "联手", "合作", "结伴", "并肩", "互相帮助", "朋友", "盟友", "兄弟"),
        RelationType.ENEMY: ("对抗", "敌人", "交手", "厮杀", "追杀", "对立", "仇敌"),
        RelationType.LOVER: ("相爱", "恋人", "道侣", "夫妻", "成婚"),
        RelationType.FAMILY: ("父亲", "母亲", "哥哥", "姐姐", "弟弟", "妹妹", "丈夫", "妻子", "儿子", "女儿"),
        RelationType.MASTER: ("拜师", "师父", "师傅", "收徒", "传授", "教导"),
        RelationType.SUBORDINATE: ("手下", "弟子", "门人", "加入", "属于", "成员"),
    }
    SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;\n]?", re.UNICODE)

    def __init__(self, learning_profile: dict[str, Any] | None = None):
        self.set_learning_profile(learning_profile)
        self._surname_chars = "".join(sorted(self.COMMON_SURNAMES))
        context = "|".join(sorted(self.PERSON_CONTEXT, key=len, reverse=True))
        self._person_pattern = re.compile(rf"(?P<name>[{re.escape(self._surname_chars)}][\u4e00-\u9fff]{{1,2}})")
        self._explicit_person_pattern = re.compile(
            r"(?:叫作|名叫|名字叫|名为|原名|自称|又称|本名|取名|名作|称作)(?P<name>[\u4e00-\u9fff]{2,6})"
        )
        self._explicit_surname_pattern = re.compile(
            r"(?:(?:^|[，。！？!?；;、：:\s])姓|(?:他|她|我|你|其|父|母|随父|随母)姓)"
            r"(?P<name>[\u4e00-\u9fff]{2,4})(?=[，。！？!?；;、：:\s的]|$)"
        )
        action = "|".join(sorted(self.ITEM_ACTIONS, key=len, reverse=True))
        self._item_action_pattern = re.compile(rf"(?:{action})(?:了|着|一把|一柄|一枚|的)?(?P<tail>[\u4e00-\u9fff]{{2,12}})")
        self._nickname_pattern = re.compile(r"(?P<name>[\u4e00-\u9fff]{1,3}(?:哥|姐|儿|爷))(?=[，。！？!?；;、：:\s]|$)")

    def set_learning_profile(self, learning_profile: dict[str, Any] | None = None) -> None:
        """Install a bounded, book-scoped profile for the next extraction run."""
        profile = dict(learning_profile or {})
        aliases = {}
        for raw_alias, raw_canonical in dict(profile.get("aliases") or {}).items():
            alias = str(raw_alias or "").strip()
            canonical = str(raw_canonical or "").strip()
            if alias and canonical and alias != canonical:
                aliases[alias] = canonical

        negative_terms = sorted(
            {
                str(term or "").strip()
                for term in profile.get("negative_terms") or []
                if str(term or "").strip()
            }
        )
        feature_weights = {}
        for raw_feature, raw_weight in dict(profile.get("feature_weights") or {}).items():
            feature = str(raw_feature or "").strip()
            if not feature:
                continue
            try:
                weight = float(raw_weight)
            except (TypeError, ValueError):
                continue
            feature_weights[feature] = max(0.5, min(1.5, weight))

        self.learning_profile = {
            "profile_version": str(profile.get("profile_version") or "").strip(),
            "aliases": aliases,
            "negative_terms": negative_terms,
            "feature_weights": feature_weights,
        }

    def extract(
        self,
        book_id: int,
        chapter_num: int,
        chapter_title: str,
        content: str,
        *,
        chapter_id: int | None = None,
    ) -> tuple[list[NovelEntity], list[NovelRelationship]]:
        normalized = self._normalize(content)
        chapter_id = int(chapter_id if chapter_id is not None else chapter_num)
        sentences = list(self._sentences(normalized))
        candidates: dict[tuple[str, EntityType], LocalCandidate] = {}
        self._extract_characters(candidates, normalized, sentences, book_id, chapter_id, chapter_num)
        self._extract_items(candidates, normalized, sentences, book_id, chapter_id, chapter_num)
        self._extract_suffix_entities(candidates, normalized, sentences, book_id, chapter_id, chapter_num)
        relationships = self._extract_relationships(book_id, chapter_id, chapter_num, sentences, candidates)
        relation_names = {
            name
            for relationship in relationships
            for name in (relationship.source_entity, relationship.target_entity)
        }
        self._finalize_candidates(candidates, relation_names)
        entities = [self._to_entity(book_id, chapter_num, candidate) for candidate in candidates.values() if candidate.status != "rejected"]
        relationships = [
            relationship
            for relationship in relationships
            if self._candidate_is_eligible(candidates, relationship.source_entity)
            and self._candidate_is_eligible(candidates, relationship.target_entity)
        ]
        return entities, relationships

    def _extract_characters(self, candidates, content, sentences, book_id, chapter_id, chapter_num):
        repeated_long_names: dict[str, list[CandidateEvidence]] = defaultdict(list)
        for start, end, sentence in sentences:
            for match in self._person_pattern.finditer(sentence):
                name, name_start, name_length = self._select_person_span(sentence, match.start())
                if not name or not self._valid_person(name) or not self._person_boundary(sentence, name_start, len(name)):
                    continue
                absolute_start = start + name_start
                evidence = self._evidence(
                    chapter_id,
                    chapter_num,
                    content,
                    absolute_start,
                    absolute_start + len(name),
                    ("surname", "context"),
                )
                if name_length >= 3:
                    repeated_long_names[name].append(evidence)
                else:
                    self._add_candidate(candidates, name, EntityType.CHARACTER, evidence, score_hint=0.45)
            for match in self._explicit_person_pattern.finditer(sentence):
                name = self._clean_name(match.group("name"))
                if self._valid_person(name) and not self._looks_like_item(name):
                    absolute_start = start + match.start("name")
                    self._add_candidate(
                        candidates,
                        name,
                        EntityType.CHARACTER,
                        self._evidence(chapter_id, chapter_num, content, absolute_start, absolute_start + len(name), ("explicit_name",)),
                        score_hint=0.8,
                    )
            for match in self._explicit_surname_pattern.finditer(sentence):
                name = self._clean_name(match.group("name"))
                if self._valid_person(name) and not self._looks_like_item(name):
                    absolute_start = start + match.start("name")
                    self._add_candidate(
                        candidates,
                        name,
                        EntityType.CHARACTER,
                        self._evidence(
                            chapter_id,
                            chapter_num,
                            content,
                            absolute_start,
                            absolute_start + len(name),
                            ("explicit_surname",),
                        ),
                        score_hint=0.8,
                    )
            for match in self._nickname_pattern.finditer(sentence):
                name = self._clean_name(match.group("name"))
                if self._valid_nickname(sentence, match.start("name"), name):
                    absolute_start = start + match.start("name")
                    self._add_candidate(
                        candidates,
                        name,
                        EntityType.CHARACTER,
                        self._evidence(chapter_id, chapter_num, content, absolute_start, absolute_start + len(name), ("nickname",)),
                        score_hint=0.4,
                    )
        variants_by_prefix: dict[str, set[str]] = defaultdict(set)
        for name in repeated_long_names:
            variants_by_prefix[name[:2]].add(name)
        for name, evidence_items in repeated_long_names.items():
            if len(evidence_items) < 2:
                continue
            short_name = name[:2]
            if short_name in self.PERSON_STOPWORDS or short_name in self.GENERIC_PERSON_TERMS:
                continue
            if len(variants_by_prefix[short_name]) > 1:
                for evidence in evidence_items:
                    self._add_candidate(
                        candidates,
                        short_name,
                        EntityType.CHARACTER,
                        evidence,
                        score_hint=0.45,
                    )
                continue
            for evidence in evidence_items:
                self._add_candidate(
                    candidates,
                    name,
                    EntityType.CHARACTER,
                    evidence,
                    score_hint=0.58,
                )

    def _extract_items(self, candidates, content, sentences, book_id, chapter_id, chapter_num):
        for start, end, sentence in sentences:
            for match in self._item_action_pattern.finditer(sentence):
                raw = match.group("tail")
                name = self._trim_to_suffix(raw, self.ITEM_SUFFIXES)
                if not name:
                    continue
                absolute_start = start + match.start("tail")
                self._add_candidate(
                    candidates,
                    name,
                    EntityType.ITEM,
                    self._evidence(chapter_id, chapter_num, content, absolute_start, absolute_start + len(name), ("item_action", "item_suffix")),
                    score_hint=0.8,
                    subtype=self._item_subtype(name),
                )

    def _extract_suffix_entities(self, candidates, content, sentences, book_id, chapter_id, chapter_num):
        known_locations = ("青云山", "蜀山", "轮回乐园", "青云宗", "魔教", "蜀山剑派", "流民")
        for start, end, sentence in sentences:
            for name in known_locations:
                cursor = sentence.find(name)
                if cursor >= 0:
                    entity_type = EntityType.FACTION if name.endswith(self.FACTION_SUFFIXES) or name in {"流民", "魔教"} else EntityType.LOCATION
                    self._add_candidate(
                        candidates,
                        name,
                        entity_type,
                        self._evidence(chapter_id, chapter_num, content, start + cursor, start + cursor + len(name), ("known_name",)),
                        score_hint=0.75,
                    )
            for suffix, entity_type in ((self.LOCATION_SUFFIXES, EntityType.LOCATION), (self.FACTION_SUFFIXES, EntityType.FACTION)):
                pattern = re.compile(rf"(?P<name>[\u4e00-\u9fff]{{2,8}}(?:{'|'.join(suffix)}))")
                for match in pattern.finditer(sentence):
                    name = self._trim_to_suffix(match.group("name"), suffix)
                    if not name or name in self.PERSON_STOPWORDS:
                        continue
                    absolute_start = start + match.start("name")
                    self._add_candidate(
                        candidates,
                        name,
                        entity_type,
                        self._evidence(chapter_id, chapter_num, content, absolute_start, absolute_start + len(name), ("location_suffix" if entity_type == EntityType.LOCATION else "faction_suffix",)),
                        score_hint=0.38,
                    )

    def _extract_relationships(self, book_id, chapter_id, chapter_num, sentences, candidates):
        characters = [candidate for (name, entity_type), candidate in candidates.items() if entity_type == EntityType.CHARACTER and candidate.status != "rejected"]
        factions = [candidate for (name, entity_type), candidate in candidates.items() if entity_type == EntityType.FACTION and candidate.status != "rejected"]
        relationships: dict[tuple[str, str, RelationType], NovelRelationship] = {}
        for start, end, sentence in sentences:
            local_chars = [candidate for candidate in characters if self._candidate_position(candidate, sentence) >= 0]
            for left, right in combinations(local_chars, 2):
                left_pos = self._candidate_position(left, sentence)
                right_pos = self._candidate_position(right, sentence)
                if left_pos < 0 or right_pos < 0:
                    continue
                lo, hi = sorted((left_pos, right_pos))
                if hi - lo - min(len(left.name), len(right.name)) > 32:
                    continue
                relation_type = self._relation_type(
                    sentence[lo + min(len(left.name), len(right.name)) : hi]
                    + sentence[hi + max(len(left.name), len(right.name)) : hi + max(len(left.name), len(right.name)) + 16]
                )
                if relation_type is None:
                    continue
                source, target = (left, right) if left_pos <= right_pos else (right, left)
                if relation_type in {RelationType.ALLY, RelationType.ENEMY, RelationType.LOVER, RelationType.FAMILY}:
                    source_name, target_name = sorted((source.name, target.name))
                else:
                    source_name, target_name = source.name, target.name
                evidence = asdict(self._evidence(chapter_id=chapter_id, chapter_num=chapter_num, content=sentence, start_offset=0, end_offset=len(sentence), features=("relation", relation_type.value)))
                key = (source_name, target_name, relation_type)
                relationships[key] = NovelRelationship(
                    book_id=book_id,
                    source_entity=source_name,
                    target_entity=target_name,
                    relation_type=relation_type,
                    description=f"{source_name}与{target_name}在正文中被明确描述为{relation_type.value}",
                    since_chapter=chapter_num,
                    confidence=0.82,
                    evidence=[evidence],
                )
            for character in local_chars:
                for faction in factions:
                    if re.search(rf"{re.escape(character.name)}(?:加入|属于|是){re.escape(faction.name)}", sentence):
                        evidence = asdict(self._evidence(chapter_id, chapter_num, sentence, 0, len(sentence), ("faction_membership",)))
                        key = (character.name, faction.name, RelationType.SUBORDINATE)
                        relationships[key] = NovelRelationship(
                            book_id=book_id,
                            source_entity=character.name,
                            target_entity=faction.name,
                            relation_type=RelationType.SUBORDINATE,
                            description=f"{character.name}属于{faction.name}",
                            since_chapter=chapter_num,
                            confidence=0.78,
                            evidence=[evidence],
                        )
        return list(relationships.values())

    def _relation_type(self, span: str) -> RelationType | None:
        for relation_type, cues in self.RELATION_CUES.items():
            if any(cue in span for cue in cues):
                return relation_type
        return None

    def _add_candidate(self, candidates, name, entity_type, evidence, *, score_hint, subtype=""):
        raw_name = self._clean_name(str(name or ""))
        canonical_name = self._canonical_name(raw_name)
        profile_negative = set(self.learning_profile.get("negative_terms", []))
        if (
            not canonical_name
            or raw_name in profile_negative
            or canonical_name in profile_negative
            or raw_name in self.PERSON_STOPWORDS
            or canonical_name in self.PERSON_STOPWORDS
        ):
            return
        weighted_score = self._weighted_score(score_hint, evidence.features)
        aliases = [raw_name] if raw_name and raw_name != canonical_name else []
        key = (canonical_name, entity_type)
        current = candidates.get(key)
        if current is None:
            candidates[key] = LocalCandidate(
                name=canonical_name,
                entity_type=entity_type,
                score=weighted_score,
                mentions=1,
                evidence=[evidence],
                aliases=aliases,
                subtype=subtype,
                status=self._status(weighted_score, 1),
            )
            return
        current.mentions += 1
        current.score = min(1.0, current.score + 0.12 * self._feature_multiplier(evidence.features))
        if evidence.text not in {item.text for item in current.evidence}:
            current.evidence.append(evidence)
        current.aliases = list(dict.fromkeys([*(current.aliases or []), *aliases]))
        if subtype and not current.subtype:
            current.subtype = subtype
        current.status = self._status(current.score, current.mentions)

    def _finalize_candidates(self, candidates, relation_names: set[str]) -> None:
        for candidate in candidates.values():
            if (
                candidate.status == "candidate"
                and candidate.mentions < 2
                and candidate.name not in relation_names
            ):
                candidate.status = "rejected"

    @staticmethod
    def _candidate_is_eligible(candidates, name: str) -> bool:
        return any(
            candidate.name == name and candidate.status != "rejected"
            for candidate in candidates.values()
        )

    def _to_entity(self, book_id, chapter_num, candidate):
        confidence = min(1.0, max(0.0, candidate.score))
        candidate.score = confidence
        description = candidate.evidence[0].text if candidate.evidence else f"章节中出现的{candidate.entity_type.value}"
        attributes = {
            "extraction_status": candidate.status,
            "confidence": round(confidence, 4),
            "subtype": candidate.subtype,
            "evidence": [asdict(item) for item in candidate.evidence[:5]],
            "mention_count": candidate.mentions,
        }
        profile_version = str(self.learning_profile.get("profile_version") or "").strip()
        if profile_version:
            attributes["learning_profile_version"] = profile_version
        return NovelEntity(
            book_id=book_id,
            name=candidate.name,
            aliases=list(candidate.aliases),
            entity_type=candidate.entity_type,
            description=description[:120],
            first_appearance_ch=chapter_num,
            last_appearance_ch=chapter_num,
            appearance_count=candidate.mentions,
            importance_score=max(1, min(5, int(round(confidence * 5)))),
            attributes=attributes,
        )

    def _canonical_name(self, name: str) -> str:
        current = str(name or "").strip()
        aliases = self.learning_profile.get("aliases") or {}
        seen = set()
        while current in aliases and current not in seen:
            seen.add(current)
            current = str(aliases[current] or "").strip()
        return current

    def _feature_multiplier(self, features: Iterable[str]) -> float:
        weights = self.learning_profile.get("feature_weights") or {}
        active = []
        for feature in features or ():
            try:
                active.append(max(0.5, min(1.5, float(weights.get(feature, 1.0)))))
            except (TypeError, ValueError):
                active.append(1.0)
        return sum(active) / len(active) if active else 1.0

    def _weighted_score(self, score_hint: float, features: Iterable[str]) -> float:
        return max(0.0, min(1.0, float(score_hint) * self._feature_multiplier(features)))

    @staticmethod
    def _candidate_position(candidate: LocalCandidate, sentence: str) -> int:
        positions = [sentence.find(candidate.name)]
        positions.extend(sentence.find(alias) for alias in candidate.aliases or [])
        valid = [position for position in positions if position >= 0]
        return min(valid) if valid else -1

    def _evidence(self, chapter_id, chapter_num, content, start_offset, end_offset, features):
        start = max(0, start_offset - 60)
        end = min(len(content), max(end_offset, start_offset) + 90)
        return CandidateEvidence(
            chapter_id=int(chapter_id),
            chapter_num=int(chapter_num),
            start_offset=int(start),
            end_offset=int(end),
            text=content[start:end].strip()[:180],
            features=tuple(features),
        )

    def _sentences(self, content) -> Iterable[tuple[int, int, str]]:
        for match in self.SENTENCE_RE.finditer(content):
            text = match.group(0).strip()
            if text:
                yield match.start(), match.end(), text

    def _valid_person(self, name):
        return (
            2 <= len(name) <= 4
            and name not in self.PERSON_STOPWORDS
            and name not in self.GENERIC_PERSON_TERMS
            and not self._looks_like_item(name)
        )

    def _select_person_span(self, sentence: str, start: int) -> tuple[str, int, int]:
        """Prefer a complete three-character name, then fall back to two."""
        if self._looks_like_title_phrase_at(sentence, start):
            return "", start, 0
        for length in (3, 2):
            name = sentence[start : start + length]
            if len(name) != length:
                continue
            if length == 3 and (name in self.PERSON_STOPWORDS or name in self.GENERIC_PERSON_TERMS):
                return "", start, 0
            if not self._valid_person(name):
                continue
            if length == 2 and name[-1] in self.ADDRESS_SUFFIXES:
                return "", start, 0
            if not all(self._is_han(char) for char in name):
                continue
            if length == 3 and sentence[start : start + 2] in self.GENERIC_PERSON_TERMS:
                continue
            if length == 3 and name[-1] in self.NAME_TAIL_STOPWORDS:
                continue
            return name, start, length
        return "", start, 0

    def _person_boundary(self, sentence: str, start: int, length: int) -> bool:
        if start > 0 and self._is_han(sentence[start - 1]) and sentence[start - 1] not in self.NAME_PREFIXES:
            return False
        return True

    def _looks_like_title_phrase_at(self, sentence: str, start: int) -> bool:
        for title in self.TITLE_PHRASES:
            if (
                sentence[start + 1 : start + 1 + len(title)] == title
                or sentence[start + 2 : start + 2 + len(title)] == title
            ):
                return True
        return False

    def _valid_nickname(self, sentence: str, start: int, name: str) -> bool:
        return bool(
            name
            and name not in self.GENERIC_PERSON_TERMS
            and name not in self.PERSON_STOPWORDS
            and "的" not in name
            and name[0] not in {"他", "她", "这", "那", "一", "每"}
            and not self._looks_like_title_phrase_at(sentence, start)
            and self._person_boundary(sentence, start, len(name))
        )

    @staticmethod
    def _is_han(char: str) -> bool:
        return bool(char) and "\u4e00" <= char <= "\u9fff"

    def _looks_like_item(self, name):
        return name.endswith(self.ITEM_SUFFIXES) and len(name) >= 3

    @staticmethod
    def _clean_name(name):
        return re.sub(r"^[‘“\"'『「【]|[’”\"'』」】]$", "", name).strip()

    @staticmethod
    def _normalize(content):
        return re.sub(r"[\u0000-\u001f\u007f]", " ", str(content or "")).replace("　", " ")

    @staticmethod
    def _trim_to_suffix(raw, suffixes):
        for index, char in enumerate(raw):
            if char in suffixes:
                value = raw[: index + 1]
                if 2 <= len(value) <= 8:
                    return value
        return ""

    @staticmethod
    def _item_subtype(name):
        if name.endswith(("剑", "刀", "枪", "戟", "弓", "甲", "盾")):
            return "weapon"
        if name.endswith(("丹", "符")):
            return "consumable"
        if name.endswith(("戒", "环", "玉", "佩", "珠", "镜", "图", "印")):
            return "artifact"
        return "object"

    @staticmethod
    def _status(score, mentions):
        if score >= 0.72 or mentions >= 3:
            return "confirmed"
        if score >= 0.35:
            return "candidate"
        return "rejected"
