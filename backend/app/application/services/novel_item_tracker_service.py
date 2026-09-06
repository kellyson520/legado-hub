from __future__ import annotations

import re
from typing import Any


class NovelItemTrackerService:
    """Open-vocabulary item, weapon, mount, prop, and artifact tracker using linguistic morphology and syntax."""

    _ITEM_LEXICON: tuple[str, ...] = (
        # Modern & Mystery items fallback
        "C4炸药", "手枪", "冲锋枪", "炸药", "手雷", "狙击枪", "手榴弹", "匕首", "短刀", "飞刀", "长剑", "长枪",
        "奥特曼面具", "卡通猫面具", "面具", "保险柜", "保险箱", "引爆器", "防弹衣", "小电脑", "水杯", "手机", "钟表", "秒表", "画稿", "钥匙", "门卡",
        # Supernatural & Mystery Artifacts
        "鬼眼", "鬼烛", "替死娃娃", "鬼绳", "黄金箱", "羊皮纸", "鬼影", "录音笔", "骨灰盒", "八音盒", "柴刀",
    )

    _CATEGORY_SUFFIXES: dict[str, tuple[str, ...]] = {
        "weapon": ("刀", "枪", "剑", "戟", "矛", "棍", "弓", "箭", "刃", "鞭", "锤", "斧", "钩", "叉", "槊", "刺", "炮", "炸药", "手枪", "冲锋枪", "狙击枪", "弹"),
        "mount": ("马", "驹", "兽", "骑", "龙", "鸟", "雕", "象", "车", "舟", "轿"),
        "armor": ("铠", "甲", "盔", "袍", "衣", "冠", "靴", "带", "盾"),
        "artifact": ("印", "玺", "幡", "旗", "镜", "鼎", "塔", "钟", "符", "丹", "石", "戒", "佩", "盒", "匣", "袋", "囊", "经", "书", "卷", "图", "针", "珠", "瓶", "壶", "杯", "药", "牌", "令", "牒", "简", "器", "物", "机", "脑", "面具"),
    }

    _ACTION_KEYWORDS: dict[str, list[str]] = {
        "acquired": ["收下", "接过", "获得", "捡起", "拿出", "摸出", "带走", "买下", "夺过", "装备", "握住", "戴上", "得到", "推进", "上了膛", "拜谢", "取下", "得获", "赐", "造得", "造就", "造了"],
        "used": ["引爆", "开枪", "射击", "扣动", "贴在", "按下", "释放", "点燃", "使用", "喝完", "戴着", "展示", "扫射", "提", "跨坐", "倒提", "横握", "拔出", "斩", "刺", "劈", "持", "挥舞", "祭出", "催动", "佩"],
        "transferred": ["递给", "交给", "送给", "扔给", "推给", "转交", "赠予", "赐予", "授予", "留给", "赏赐", "献给"],
        "lost": ["丢失", "被夺", "毁坏", "炸碎", "丢弃", "扔掉", "损毁", "折断"],
    }

    def __init__(self):
        self._sorted_lexicon = sorted(self._ITEM_LEXICON, key=len, reverse=True)
        # Syntactic patterns
        self._p_quant = re.compile(
            r"(?:造得|造就|造了|得|有一|有|佩|持|带|跨)?(?P<quant>[一两二三四五六七八九十百千万数几]+(?P<classifier>柄|把|副|杆|口|匹|只|头|对|双|块|卷|轴|张|尊|顶|件|具|枝|架|门|枚|方|条|面|领|支|颗))(?P<item>[\u4e00-\u9fff]{2,8}?)(?=[，。！？、；\s\n]|重|长|阔|名|又名|号|赠|赐|送|与|给|交|献|托|$)"
        )
        self._p_gov = re.compile(
            r"(?P<action_verb>手提|倒提|横握|手持|手按|手握|腰悬|腰佩|身披|头戴|跨坐|骑坐|掣出|拔出|按出|掏出|取出|祭出|祭起|亮出|挥舞|催动|掷出|佩带)(?:了|着|起)?(?P<item>[\u4e00-\u9fff]{2,8}?)(?=[，。！？、；\s\n]|向|朝|斩|刺|劈|砸|射|击|杀|去|而|来|将|与|迎|呼|$)"
        )
        self._p_transfer = re.compile(
            r"(?:将|把|以)(?:[一两二三四五六七八九十百千万数几]+[柄把副杆口匹只头对双块卷轴张尊顶件具枝架门枚方条面领支颗])?(?P<item>[\u4e00-\u9fff]{2,8}?)(?P<trans_verb>赐予|赠予|授予|赠与|授与|交付|献给|送与|留给|赏赐|托付|遗下|奉上|递给|交给|送给)(?P<target>[\u4e00-\u9fff]{2,4})"
        )
        self._quant_prefix = re.compile(
            r"^[一两二三四五六七八九十百千万数几]+(?:柄|把|副|杆|口|匹|只|头|对|双|块|卷|轴|张|尊|顶|件|具|枝|架|门|枚|方|条|面|领|支|颗)"
        )

    def _classify_item(self, item_name: str) -> str:
        for cat, suffixes in self._CATEGORY_SUFFIXES.items():
            if any(item_name.endswith(s) for s in suffixes):
                return cat
        return "artifact"

    def track_items(
        self,
        chapters: list[dict[str, Any]],
        character_names: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Scans chapters and attributes item interactions to respective characters using open morphology."""
        results: dict[str, list[dict[str, Any]]] = {name: [] for name in character_names}
        split_pattern = re.compile(r"[。！？\n；]")

        for chapter in chapters:
            content = str(chapter.get("content", ""))
            chapter_index = int(chapter.get("chapter_index", 0))
            chapter_title = str(chapter.get("title", ""))

            active_char: str | None = None
            sentences = [s.strip() for s in split_pattern.split(content) if s.strip()]
            for sentence in sentences:
                matched_chars = [name for name in character_names if name in sentence]
                if matched_chars:
                    active_char = matched_chars[0]
                elif active_char and any(p in sentence for p in ("他", "她", "自己")):
                    matched_chars = [active_char]

                found_items_with_action: list[tuple[str, str, str]] = []  # (item, action, category)

                # 1. Check transfer pattern (e.g. 曹操将赤兔马赠予关羽)
                for tm in self._p_transfer.finditer(sentence):
                    t_item = self._quant_prefix.sub("", tm.group("item")).strip()
                    t_target = tm.group("target").strip()
                    if t_item and any(t_item.endswith(s) for cat in self._CATEGORY_SUFFIXES.values() for s in cat):
                        cat = self._classify_item(t_item)
                        # The giver transferred, the target acquired
                        if t_target in character_names:
                            results[t_target].append({
                                "item_name": t_item,
                                "action": "acquired",
                                "category": cat,
                                "chapter_index": chapter_index,
                                "chapter_title": chapter_title,
                                "excerpt": sentence[:160],
                            })
                        found_items_with_action.append((t_item, "transferred", cat))

                # 2. Check quantitative classifier pattern
                for qm in self._p_quant.finditer(sentence):
                    raw_item = self._quant_prefix.sub("", qm.group("item")).strip()
                    if raw_item and any(raw_item.endswith(s) for cat in self._CATEGORY_SUFFIXES.values() for s in cat):
                        cat = self._classify_item(raw_item)
                        found_items_with_action.append((raw_item, "acquired", cat))

                # 3. Check action-governed slot pattern
                for gm in self._p_gov.finditer(sentence):
                    raw_item = self._quant_prefix.sub("", gm.group("item")).strip()
                    verb = gm.group("action_verb")
                    if raw_item and any(raw_item.endswith(s) for cat in self._CATEGORY_SUFFIXES.values() for s in cat):
                        cat = self._classify_item(raw_item)
                        act = "used" if any(v in verb for v in ("持", "提", "握", "拔", "斩", "刺", "舞", "跨", "祭")) else "acquired"
                        found_items_with_action.append((raw_item, act, cat))

                # 4. Check static lexicon fallback
                for lex in self._sorted_lexicon:
                    if lex in sentence:
                        cat = self._classify_item(lex)
                        found_items_with_action.append((lex, "used", cat))

                if not found_items_with_action or not matched_chars:
                    continue

                # Filter sub-strings (e.g. keep 青龙偃月刀, remove 刀)
                unique_items: dict[str, tuple[str, str]] = {}
                for itm, act, cat in found_items_with_action:
                    if itm in unique_items:
                        continue
                    unique_items[itm] = (act, cat)

                final_items = []
                for itm, (act, cat) in unique_items.items():
                    if not any(other != itm and itm in other for other in unique_items):
                        final_items.append((itm, act, cat))

                for char in matched_chars:
                    for itm, act, cat in final_items:
                        # Determine fine action if generic
                        final_act = act
                        for act_type, kws in self._ACTION_KEYWORDS.items():
                            if any(kw in sentence for kw in kws):
                                final_act = act_type
                                break

                        results[char].append({
                            "item_name": itm,
                            "action": final_act,
                            "category": cat,
                            "chapter_index": chapter_index,
                            "chapter_title": chapter_title,
                            "excerpt": sentence[:160],
                        })

        # Deduplicate identical actions within the same chapter
        cleaned: dict[str, list[dict[str, Any]]] = {}
        for char, records in results.items():
            seen: set[tuple[str, str, int]] = set()
            unique_records = []
            for r in records:
                key = (r["item_name"], r["action"], r["chapter_index"])
                if key not in seen:
                    seen.add(key)
                    unique_records.append(r)
            cleaned[char] = unique_records

        return cleaned
