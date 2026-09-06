from __future__ import annotations

import re
from typing import Any


class NovelEmotionalArcService:
    """Extracts emotional trajectories, sentiment polarity, and psychological turning points for characters."""

    _EMOTION_LEXICON: dict[str, tuple[float, str]] = {
        # Positive / Calm / Confident (Weight > 0)
        "从容": (1.5, "从容"),
        "平静": (1.2, "平静"),
        "悠闲": (1.0, "悠闲"),
        "自信": (1.5, "自信"),
        "微笑": (1.0, "从容"),
        "冷静": (1.2, "冷静"),
        "欣喜": (1.2, "欣喜"),
        "安宁": (1.0, "平静"),
        "镇定": (1.2, "从容"),
        "果断": (1.2, "自信"),
        "从容不迫": (1.8, "从容"),
        "轻松": (1.0, "悠闲"),
        # Negative / Despair / Panic (Weight < 0)
        "恐惧": (-2.0, "恐惧"),
        "绝望": (-2.5, "绝望"),
        "冷汗": (-1.5, "紧张"),
        "惨白": (-1.5, "恐惧"),
        "心跳骤停": (-2.0, "恐惧"),
        "崩塌": (-1.5, "绝望"),
        "惨叫": (-2.0, "恐惧"),
        "惊恐": (-2.0, "恐惧"),
        "慌乱": (-1.5, "紧张"),
        "崩溃": (-2.5, "绝望"),
        "痛苦": (-1.8, "痛苦"),
        "无力": (-1.5, "绝望"),
        # Resolute / Combat focus
        "冷冽": (0.8, "果断"),
        "反击": (1.2, "果断"),
        "杀气": (0.5, "愤怒"),
        "死战": (0.6, "果断"),
    }

    def compute_arc(
        self,
        chapters: list[dict[str, Any]],
        character_name: str,
    ) -> dict[str, Any]:
        """Calculates chapter-by-chapter emotional trajectory and turning points."""
        trajectory: list[dict[str, Any]] = []
        split_pattern = re.compile(r"[。！？\n；]")

        for chapter in chapters:
            content = str(chapter.get("content", ""))
            chapter_index = int(chapter.get("chapter_index", 0))
            chapter_title = str(chapter.get("title", ""))

            sentences = [s.strip() for s in split_pattern.split(content) if s.strip()]
            relevant_sentences: list[str] = []
            active = False

            for s in sentences:
                if character_name in s:
                    active = True
                    relevant_sentences.append(s)
                elif active and any(p in s for p in ("他", "她", "自己")):
                    relevant_sentences.append(s)
                else:
                    active = False

            target_text = " ".join(relevant_sentences) if relevant_sentences else content

            score = 0.0
            emotion_counts: dict[str, int] = {}
            for word, (weight, emotion_label) in self._EMOTION_LEXICON.items():
                c = target_text.count(word)
                if c > 0:
                    score += weight * c
                    emotion_counts[emotion_label] = emotion_counts.get(emotion_label, 0) + c

            if emotion_counts:
                dominant_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0]
            else:
                dominant_emotion = "平静"

            trajectory.append({
                "chapter_index": chapter_index,
                "chapter_title": chapter_title,
                "sentiment_score": round(score, 2),
                "dominant_emotion": dominant_emotion,
                "excerpt": (relevant_sentences[0] if relevant_sentences else content[:120]),
            })

        # Find turning points (significant sentiment delta between adjacent chapters)
        turning_points: list[dict[str, Any]] = []
        for i in range(1, len(trajectory)):
            prev = trajectory[i - 1]["sentiment_score"]
            curr = trajectory[i]["sentiment_score"]
            delta = curr - prev
            if abs(delta) >= 1.5 or (prev > 0 and curr < 0) or (prev < 0 and curr > 0):
                turning_points.append({
                    "chapter_index": trajectory[i]["chapter_index"],
                    "chapter_title": trajectory[i]["chapter_title"],
                    "from_score": prev,
                    "to_score": curr,
                    "delta": round(delta, 2),
                    "shift": "plummet" if delta < 0 else "surge",
                    "description": f"从【{trajectory[i-1]['dominant_emotion']}】转向【{trajectory[i]['dominant_emotion']}】",
                })

        # Dominant overall sentiment
        all_scores = [t["sentiment_score"] for t in trajectory]
        avg_score = sum(all_scores) / max(len(all_scores), 1)
        if avg_score > 0.5:
            overall_sentiment = "积极从容"
        elif avg_score < -0.5:
            overall_sentiment = "危机紧迫"
        else:
            overall_sentiment = "波澜起伏"

        return {
            "character_name": character_name,
            "overall_sentiment": overall_sentiment,
            "trajectory": trajectory,
            "turning_points": turning_points,
        }
