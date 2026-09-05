"""
书源健康评分与状态判定
"""

from ..entities.novel import NovelSourceMirror


class SourceHealthScore:
    """书源健康评分器"""

    @classmethod
    def calculate(cls, mirror: NovelSourceMirror) -> float:
        score = 100.0
        score -= min(50, mirror.failure_count ** 2 * 2)
        if mirror.avg_response_ms > 5000:
            score -= min(30, (mirror.avg_response_ms - 5000) / 100)
        if mirror.total_chapters_available > 0:
            missing_rate = 1 - (mirror.chapters_fetched / mirror.total_chapters_available)
            score -= missing_rate * 40
        return max(0.0, min(100.0, score))

    @classmethod
    def determine_status(cls, mirror: NovelSourceMirror) -> str:
        score = cls.calculate(mirror)
        if mirror.failure_count >= 10 or score < 20:
            return "failed"
        if mirror.failure_count >= 5 or score < 50:
            return "degraded"
        return "active"
