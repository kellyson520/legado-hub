"""
内容对比与合并算法

多源内容对比：
- 文本相似度计算（基于字符级 n-gram 和句子级重叠）
- 质量评分（长度、完整性、错字率估计）
- 多源合并策略（取最优、或合并去重）
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class ContentQuality:
    """内容质量评分"""
    score: float = 0.0  # 0-100
    word_count: int = 0
    paragraph_count: int = 0
    has_chapter_header: bool = False
    has_chapter_footer: bool = False
    error_estimate: float = 0.0  # 估计错字率
    completeness: float = 0.0  # 完整度估计


@dataclass
class ContentMergeResult:
    """内容合并结果"""
    content: str
    quality_score: float
    word_count: int
    merged_from: List[str] = field(default_factory=list)
    source_scores: Dict[str, float] = field(default_factory=dict)
    merge_strategy: str = "best"  # best / majority / hybrid


class ContentComparator:
    """内容对比器 - 计算两段文本的相似度"""

    @staticmethod
    def similarity(a: str, b: str) -> float:
        """
        计算两段文本的相似度 (0-1)

        综合多种指标：
        - 字符级 Jaccard 相似度
        - 句子级重叠率
        - 字数比例
        """
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        # 1. 字符级 2-gram Jaccard 相似度
        char_sim = ContentComparator._ngram_jaccard(a, b, 2)

        # 2. 句子级重叠
        sent_sim = ContentComparator._sentence_overlap(a, b)

        # 3. 字数比例（越接近越可能是同一章节）
        len_a = len(a)
        len_b = len(b)
        len_ratio = min(len_a, len_b) / max(len_a, len_b) if max(len_a, len_b) > 0 else 0

        # 加权综合
        return char_sim * 0.5 + sent_sim * 0.3 + len_ratio * 0.2

    @staticmethod
    def _ngram_jaccard(a: str, b: str, n: int = 2) -> float:
        """n-gram Jaccard 相似度"""
        def get_ngrams(text: str, n: int) -> set:
            text = re.sub(r'\s+', '', text)
            if len(text) < n:
                return set(text)
            return set(text[i:i+n] for i in range(len(text) - n + 1))

        set_a = get_ngrams(a, n)
        set_b = get_ngrams(b, n)
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    @staticmethod
    def _sentence_overlap(a: str, b: str) -> float:
        """句子级重叠率"""
        def split_sentences(text: str) -> set:
            # 按句末标点切分
            sentences = re.split(r'[。！？!?\n]', text)
            return set(s.strip() for s in sentences if len(s.strip()) >= 5)

        sents_a = split_sentences(a)
        sents_b = split_sentences(b)
        if not sents_a or not sents_b:
            return 0.0
        intersection = sents_a & sents_b
        return len(intersection) / max(len(sents_a), len(sents_b))


class ContentQualityEstimator:
    """内容质量评估器"""

    # 常见广告/垃圾内容模式
    AD_PATTERNS = [
        r'百度搜索|谷歌搜索|笔趣阁|找小说|更新最快',
        r'手机版|电脑版|返回目录|加入书架|推荐投票',
        r'https?://[^\s]+',
        r'[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+\.[a-zA-Z]+',
        r'本章未完，点击下一页',
        r'^\s*第[一二三四五六七八九十百千\d]+章.*$',  # 章节标题（不应在正文中重复出现）
    ]

    @classmethod
    def evaluate(cls, content: str) -> ContentQuality:
        """
        评估章节内容质量

        评分维度：
        - 字数（合理区间得分高）
        - 段落结构（有分段得分高）
        - 广告/垃圾内容占比
        - 完整性（有头有尾）
        - 错字率估计（基于常见错字模式）
        """
        if not content or not content.strip():
            return ContentQuality(score=0.0)

        word_count = len(re.sub(r'\s+', '', content))
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        paragraph_count = len(paragraphs)

        # 1. 字数得分（正常章节 2000-5000 字最优）
        if word_count < 500:
            word_score = 20.0
        elif word_count < 1000:
            word_score = 40.0
        elif word_count < 2000:
            word_score = 60.0
        elif word_count <= 5000:
            word_score = 90.0
        elif word_count <= 10000:
            word_score = 70.0
        else:
            word_score = 50.0

        # 2. 段落结构得分
        if paragraph_count >= 10:
            para_score = 90.0
        elif paragraph_count >= 5:
            para_score = 70.0
        elif paragraph_count >= 2:
            para_score = 50.0
        else:
            para_score = 20.0

        # 3. 广告占比（越低越好）
        ad_chars = 0
        for pattern in cls.AD_PATTERNS:
            matches = re.findall(pattern, content)
            ad_chars += sum(len(m) for m in matches)
        ad_ratio = ad_chars / max(word_count, 1)
        ad_score = max(0.0, 100.0 - ad_ratio * 500.0)

        # 4. 完整性估计
        completeness = cls._estimate_completeness(content, word_count)

        # 5. 错字率估计（基于常见错字模式，粗略估计）
        error_estimate = cls._estimate_errors(content)
        error_score = max(0.0, 100.0 - error_estimate * 1000)

        # 综合评分
        total_score = (
            word_score * 0.25
            + para_score * 0.15
            + ad_score * 0.25
            + completeness * 100 * 0.2
            + error_score * 0.15
        )
        total_score = min(100.0, max(0.0, total_score))

        return ContentQuality(
            score=total_score,
            word_count=word_count,
            paragraph_count=paragraph_count,
            error_estimate=error_estimate,
            completeness=completeness,
        )

    @classmethod
    def _estimate_completeness(cls, content: str, word_count: int) -> float:
        """估计章节完整度"""
        score = 0.5  # 基准 0.5

        # 结尾模式（有完整结尾的加分）
        ending_patterns = [
            r'。$', r'！$', r'？$', r'」$', r'』$',
            r'未完待续', r'敬请期待', r'下章待续',
        ]
        stripped = content.strip()
        for pat in ending_patterns:
            if re.search(pat, stripped[-10:] if len(stripped) > 10 else stripped):
                score += 0.2
                break

        # 开头有内容（不是只有标题）
        if word_count > 100:
            score += 0.2

        # 字数在合理区间
        if 2000 <= word_count <= 8000:
            score += 0.1

        return min(1.0, max(0.0, score))

    @classmethod
    def _estimate_errors(cls, content: str) -> float:
        """估计错字率（每千字错字数，粗略估计）"""
        if not content:
            return 0.0

        # 常见 OCR/输入错误模式
        error_patterns = [
            r'[a-zA-Z]{2,}',  # 中英文混杂（可能是识别错误）
            r'[^\u4e00-\u9fff，。！？、；：""''（）《》\w\s]',  # 异常符号
        ]

        error_chars = 0
        for pat in error_patterns:
            matches = re.findall(pat, content)
            error_chars += sum(len(m) for m in matches)

        total_chars = max(len(content), 1)
        return error_chars / total_chars


class ContentMerger:
    """多源内容合并器"""

    @staticmethod
    def merge(
        sources: List[Dict[str, Any]],
        strategy: str = "hybrid",
    ) -> ContentMergeResult:
        """
        合并多个来源的内容

        Args:
            sources: [{"source_url": "...", "content": "...", "source_name": "...", "word_count": int}, ...]
            strategy: 合并策略
                - best: 取质量最高的
                - majority: 多数投票（相同内容最多的）
                - hybrid: 混合策略（先用质量评分选 top N，再对比相似度）

        Returns:
            ContentMergeResult
        """
        # 过滤空内容
        valid_sources = [s for s in sources if s.get("content", "").strip()]
        if not valid_sources:
            return ContentMergeResult(
                content="",
                quality_score=0.0,
                word_count=0,
                merge_strategy=strategy,
            )

        # 为每个来源评估质量
        quality_map = {}
        for s in valid_sources:
            quality = ContentQualityEstimator.evaluate(s["content"])
            quality_map[s["source_url"]] = quality.score

        # 按策略合并
        if strategy == "best":
            return ContentMerger._merge_best(valid_sources, quality_map)
        elif strategy == "majority":
            return ContentMerger._merge_majority(valid_sources, quality_map)
        else:  # hybrid
            return ContentMerger._merge_hybrid(valid_sources, quality_map)

    @staticmethod
    def _merge_best(sources, quality_map) -> ContentMergeResult:
        """取质量最高的"""
        best = max(sources, key=lambda s: quality_map.get(s["source_url"], 0))
        best_quality = quality_map.get(best["source_url"], 0)
        return ContentMergeResult(
            content=best["content"],
            quality_score=best_quality,
            word_count=len(re.sub(r'\s+', '', best["content"])),
            merged_from=[best["source_url"]],
            source_scores=quality_map,
            merge_strategy="best",
        )

    @staticmethod
    def _merge_majority(sources, quality_map) -> ContentMergeResult:
        """
        多数投票：找到内容最相似的聚类，取聚类中质量最高的

        算法：
        1. 两两计算相似度，构建相似度图
        2. 找到最大的相似聚类（相似度 >= 0.7）
        3. 在聚类中取质量最高的
        """
        n = len(sources)
        if n == 1:
            return ContentMerger._merge_best(sources, quality_map)

        # 相似度矩阵
        sim_matrix = {}
        for i in range(n):
            for j in range(i + 1, n):
                sim = ContentComparator.similarity(sources[i]["content"], sources[j]["content"])
                sim_matrix[(i, j)] = sim
                sim_matrix[(j, i)] = sim

        # 简单聚类：找和大多数相似的
        best_cluster_idx = -1
        max_cluster_size = 0

        for i in range(n):
            cluster_size = 1
            for j in range(n):
                if i != j and sim_matrix.get((i, j), 0) >= 0.7:
                    cluster_size += 1
            if cluster_size > max_cluster_size:
                max_cluster_size = cluster_size
                best_cluster_idx = i

        # 找出这个聚类中质量最高的
        cluster_members = [best_cluster_idx]
        for j in range(n):
            if j != best_cluster_idx and sim_matrix.get((best_cluster_idx, j), 0) >= 0.7:
                cluster_members.append(j)

        best_idx = max(cluster_members, key=lambda i: quality_map.get(sources[i]["source_url"], 0))
        best = sources[best_idx]
        best_quality = quality_map.get(best["source_url"], 0)

        return ContentMergeResult(
            content=best["content"],
            quality_score=best_quality + min(10.0, max_cluster_size * 2.0),  # 多数加分
            word_count=len(re.sub(r'\s+', '', best["content"])),
            merged_from=[sources[i]["source_url"] for i in cluster_members],
            source_scores=quality_map,
            merge_strategy="majority",
        )

    @staticmethod
    def _merge_hybrid(sources, quality_map) -> ContentMergeResult:
        """
        混合策略：
        1. 先按质量排序取 top 50%
        2. 在 top 中找多数聚类
        3. 取聚类中质量最高的
        """
        n = len(sources)
        if n <= 2:
            return ContentMerger._merge_best(sources, quality_map)

        # 按质量排序，取 top half
        sorted_sources = sorted(sources, key=lambda s: quality_map.get(s["source_url"], 0), reverse=True)
        top_count = max(2, n // 2)
        top_sources = sorted_sources[:top_count]

        # 在 top 中用 majority 策略
        top_quality_map = {s["source_url"]: quality_map[s["source_url"]] for s in top_sources}
        return ContentMerger._merge_majority(top_sources, top_quality_map)
