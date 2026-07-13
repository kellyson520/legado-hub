"""
BM25 倒排索引（基于 jieba 分词）

纯本地实现，无需外部 API。
支持：章节文本、实体描述、事件描述的倒排索引。
"""

import math
import re
from typing import List, Dict, Tuple
from collections import Counter, defaultdict

import jieba


class BM25Index:
    """BM25 倒排索引"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[str] = []
        self.doc_tokens: List[List[str]] = []
        self.doc_lengths: List[int] = []
        self.doc_ids: List[int] = []  # internal_id -> external doc_id
        self.avgdl: float = 0.0
        self.idf: Dict[str, float] = {}
        self.inverted_index: Dict[str, List[int]] = defaultdict(list)
        self._built = False

    def add_document(self, doc_id: int, text: str):
        """添加文档到索引"""
        tokens = self._tokenize(text)
        internal_id = len(self.documents)
        self.documents.append(text)
        self.doc_tokens.append(tokens)
        self.doc_lengths.append(len(tokens))
        self.doc_ids.append(doc_id)

        for token in set(tokens):
            self.inverted_index[token].append(internal_id)

    def build(self):
        """构建索引（计算 IDF）"""
        N = len(self.documents)
        if N == 0:
            return

        self.avgdl = sum(self.doc_lengths) / N

        # 计算 IDF
        for token, docs in self.inverted_index.items():
            df = len(docs)
            self.idf[token] = math.log((N - df + 0.5) / (df + 0.5) + 1)

        self._built = True

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """BM25 检索，返回 (doc_id, score) 列表"""
        if not self._built:
            self.build()

        query_tokens = self._tokenize(query)
        scores: Dict[int, float] = defaultdict(float)

        for token in query_tokens:
            if token not in self.idf:
                continue
            idf = self.idf[token]
            for doc_id in self.inverted_index.get(token, []):
                tf = self.doc_tokens[doc_id].count(token)
                dl = self.doc_lengths[doc_id]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                if denom > 0:
                    score = idf * (tf * (self.k1 + 1)) / denom
                    scores[doc_id] += score

        results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        # 转换 internal_id -> external doc_id
        return [(self.doc_ids[internal_id], score) for internal_id, score in results[:top_k]]

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """jieba 分词 + 过滤"""
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', ' ', text)
        tokens = list(jieba.cut_for_search(text))
        # 过滤停用词和过短词
        stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        return [t.strip().lower() for t in tokens if len(t.strip()) > 1 and t.strip() not in stopwords]
