from __future__ import annotations

import re
from typing import Any


class NovelSceneTensionService:
    """Calculates narrative tension curves and extracts peak climax scenes using conflict density."""

    # High-impact conflict keywords with assigned tension weights
    _TENSION_WEIGHTS: dict[str, float] = {
        "爆炸": 4.0, "炸药": 4.0, "炸裂": 3.5, "轰": 3.0, "砰": 3.0,
        "枪": 3.5, "子弹": 3.0, "开枪": 3.5, "扫射": 4.0, "扣动扳机": 4.0,
        "杀": 3.0, "死": 2.5, "鲜血": 3.5, "撕裂": 3.0, "惨叫": 3.0,
        "厉鬼": 4.0, "鬼": 2.0, "复苏": 2.5, "袭击": 3.0, "重伤": 3.0,
        "危机": 2.5, "千钧一发": 3.5, "生死关头": 4.0, "绝望": 2.5, "恐惧": 2.5,
        "反击": 2.5, "吞没": 2.5, "毁灭": 3.0, "倒计时": 3.0, "火光": 2.5,
    }

    _PUNCTUATION_WEIGHTS: dict[str, float] = {
        "！": 0.8,
        "!": 0.8,
        "……": 0.3,
        "？": 0.4,
    }

    def score_passage(self, text: str) -> float:
        """Computes narrative conflict and tension score for a given text snippet."""
        if not text:
            return 0.0

        score = 0.0
        for word, weight in self._TENSION_WEIGHTS.items():
            count = text.count(word)
            if count > 0:
                score += weight * min(count, 4)

        for punct, weight in self._PUNCTUATION_WEIGHTS.items():
            count = text.count(punct)
            if count > 0:
                score += weight * min(count, 8)

        # Normalize slightly by length to prevent sheer text volume inflation
        length_factor = max(len(text) / 200.0, 0.5)
        raw_density = score / length_factor
        return round(score, 2)

    def extract_climax_scenes(
        self,
        chapters: list[dict[str, Any]],
        top_k: int = 3,
        window_size: int = 300,
        stride: int = 150,
    ) -> list[dict[str, Any]]:
        """Scans chapter texts with sliding windows to identify peak narrative conflict scenes."""
        candidate_scenes: list[dict[str, Any]] = []

        for chapter in chapters:
            content = str(chapter.get("content", ""))
            if not content:
                continue

            chapter_id = str(chapter.get("chapter_id", ""))
            chapter_index = int(chapter.get("chapter_index", 0))
            chapter_title = str(chapter.get("title", ""))

            # Sliding window over content
            best_window_score = 0.0
            best_window_excerpt = ""
            best_window_offset = 0

            text_len = len(content)
            for start in range(0, max(text_len - window_size + 1, 1), stride):
                end = min(start + window_size, text_len)
                window_text = content[start:end].strip()
                score = self.score_passage(window_text)

                if score > best_window_score:
                    best_window_score = score
                    best_window_excerpt = window_text
                    best_window_offset = start

            if best_window_score > 0.0:
                candidate_scenes.append({
                    "chapter_id": chapter_id,
                    "chapter_index": chapter_index,
                    "chapter_title": chapter_title,
                    "tension_score": best_window_score,
                    "offset": best_window_offset,
                    "excerpt": best_window_excerpt,
                })

        candidate_scenes.sort(key=lambda s: s["tension_score"], reverse=True)
        return candidate_scenes[:top_k]
