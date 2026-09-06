from __future__ import annotations

import re
from typing import Any


class NovelItemTrackerService:
    """Tracks items, weapons, props, and artifacts associated with novel characters."""

    _ITEM_LEXICON: tuple[str, ...] = (
        # Weapons & Explosives
        "C4炸药", "手枪", "冲锋枪", "炸药", "手雷", "狙击枪", "手榴弹", "匕首", "短刀", "飞刀", "长剑", "长枪",
        # Special Props & Gear
        "奥特曼面具", "卡通猫面具", "面具", "保险柜", "保险箱", "引爆器", "防弹衣", "小电脑", "水杯", "手机", "钟表", "秒表", "画稿", "钥匙", "门卡",
        # Supernatural & Mystery Artifacts
        "鬼眼", "鬼烛", "替死娃娃", "鬼绳", "黄金箱", "羊皮纸", "鬼影", "录音笔", "骨灰盒", "八音盒", "柴刀",
    )

    _ACTION_KEYWORDS: dict[str, list[str]] = {
        "acquired": ["收下", "接过", "获得", "捡起", "拿出", "摸出", "带走", "买下", "夺过", "装备", "握住", "戴上", "得到", "推进", "上了膛"],
        "used": ["引爆", "开枪", "射击", "扣动", "贴在", "按下", "释放", "点燃", "使用", "喝完", "戴着", "展示", "扫射"],
        "transferred": ["递给", "交给", "送给", "扔给", "推给", "转交"],
        "lost": ["丢失", "被夺", "毁坏", "炸碎", "丢弃", "扔掉", "损毁"],
    }

    def __init__(self):
        # Sort items by length descending so "C4炸药" is checked before "炸药"
        self._sorted_items = sorted(self._ITEM_LEXICON, key=len, reverse=True)

    def track_items(
        self,
        chapters: list[dict[str, Any]],
        character_names: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Scans chapters and attributes item interactions to respective characters."""
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

                matched_items = [item for item in self._sorted_items if item in sentence]
                if not matched_items or not matched_chars:
                    continue

                # Filter sub-strings, e.g. keep "C4炸药", discard "炸药" if "C4炸药" matched
                filtered_items: list[str] = []
                for item in matched_items:
                    if not any(other != item and item in other for other in matched_items):
                        filtered_items.append(item)

                # Determine action
                action = "used"
                for act_type, kws in self._ACTION_KEYWORDS.items():
                    if any(kw in sentence for kw in kws):
                        action = act_type
                        break

                for item in filtered_items:
                    for char in matched_chars:
                        results[char].append({
                            "item_name": item,
                            "action": action,
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
