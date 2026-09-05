"""
文本处理管线 - Text Pipeline

Legado 书源中常见的文本后处理操作：
- 替换规则（replaceRule）
- 正则提取
- HTML 标签清理
- 繁简转换
- 去广告
- 段落格式化
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


def _python_replacement(replacement: str) -> str:
    return re.sub(r'\$(\d+)', r'\\\1', replacement)


def apply_rule_operations(values: list[str], operations: list[dict]) -> list[str]:
    result = [str(value) for value in values if value is not None]
    for operation in operations:
        kind = operation.get("kind")
        if kind == "replace":
            result = [value.replace(operation.get("old", ""), operation.get("new", "")) for value in result]
        elif kind == "regex_replace":
            pattern = operation.get("pattern", "")
            replacement = _python_replacement(operation.get("replacement", ""))
            transformed: list[str] = []
            for value in result:
                try:
                    transformed.append(re.sub(pattern, replacement, value))
                except re.error:
                    transformed.append(value)
            result = transformed
    return result


@dataclass
class ReplaceRule:
    """替换规则"""
    pattern: str
    replacement: str
    is_regex: bool = True
    enabled: bool = True


class TextPipeline:
    """
    文本处理管线

    支持链式调用各种文本处理操作
    """

    # 常见广告/垃圾内容模式
    DEFAULT_AD_PATTERNS = [
        r'百度搜索.*?最新章节',
        r'手机版.*?阅读网址',
        r'https?://[^\s\u4e00-\u9fff]+',
        r'www\.[a-zA-Z0-9_-]+\.[a-zA-Z]{2,}',
        r'[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+\.[a-zA-Z]+',
        r'本章未完.*?点击下一页',
        r'加入书架.*?推荐投票',
        r'笔趣阁.*?找小说',
        r'更新最快.*?最稳定',
    ]

    # 章节标题模式
    CHAPTER_TITLE_PATTERNS = [
        r'^\s*第[一二三四五六七八九十百千\d]+[章节卷集部][\s：:、.].*$',
        r'^\s*[一二三四五六七八九十百千\d]+、.*$',
        r'^\s*[Cc]hapter\s*\d+.*$',
    ]

    def __init__(self):
        self._rules: List[ReplaceRule] = []

    def add_rule(self, pattern: str, replacement: str, is_regex: bool = True) -> 'TextPipeline':
        """添加替换规则"""
        self._rules.append(ReplaceRule(pattern, replacement, is_regex))
        return self

    def add_rules_from_config(self, rules_config: Any) -> 'TextPipeline':
        """
        从 Legado 配置加载替换规则

        replaceRule 可以是：
        - 字符串：pattern|||replacement 格式
        - 列表：[{"pattern": "...", "replacement": "...", "isRegex": true}, ...]
        - dict：键值对形式
        """
        if not rules_config:
            return self

        if isinstance(rules_config, list):
            for rule in rules_config:
                if isinstance(rule, dict):
                    pattern = str(rule.get('pattern', ''))
                    replacement = str(rule.get('replacement', ''))
                    is_regex = bool(rule.get('isRegex', True))
                    enabled = bool(rule.get('enabled', True))
                    if enabled and pattern:
                        self.add_rule(pattern, replacement, is_regex)
                elif isinstance(rule, str) and '|||' in rule:
                    parts = rule.split('|||', 1)
                    if len(parts) == 2:
                        self.add_rule(parts[0], parts[1], True)

        elif isinstance(rules_config, dict):
            for pattern, replacement in rules_config.items():
                self.add_rule(str(pattern), str(replacement), True)

        elif isinstance(rules_config, str):
            # 支持 ## 格式的 replaceRegex（Legado 特有）
            # 格式: ##regex 或 ##regex##replacement（用 ## 分隔）
            # 多行时每行一条规则
            for line in rules_config.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('##'):
                    rest = line[2:]
                    if '##' in rest:
                        # ##regex##replacement 格式
                        parts = rest.split('##', 1)
                        self.add_rule(parts[0], parts[1], True)
                    else:
                        # ##regex 格式（删除匹配，replacement 为空）
                        self.add_rule(rest, '', True)
                elif '|||' in line:
                    parts = line.split('|||', 1)
                    self.add_rule(parts[0], parts[1], True)

        return self

    def process(self, text: str) -> str:
        """执行完整的文本处理管线"""
        if not text:
            return ''

        result = text

        # 1. 应用替换规则
        result = self._apply_replace_rules(result)

        # 2. HTML 标签清理（如果需要）
        if '<' in result and '>' in result:
            result = self.strip_html_tags(result)

        # 3. 转义字符还原
        result = self._unescape(result)

        # 4. 段落格式化
        result = self.format_paragraphs(result)

        return result

    def _apply_replace_rules(self, text: str) -> str:
        """应用替换规则"""
        result = text
        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                if rule.is_regex:
                    result = re.sub(rule.pattern, rule.replacement, result)
                else:
                    result = result.replace(rule.pattern, rule.replacement)
            except re.error:
                # 正则错误，跳过
                continue
        return result

    @staticmethod
    def strip_html_tags(text: str) -> str:
        """移除 HTML 标签"""
        if not text:
            return ''
        # 替换 <br> 为换行
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
        # 移除其他标签
        text = re.sub(r'<[^>]+>', '', text)
        return text

    @staticmethod
    def _unescape(text: str) -> str:
        """还原转义字符"""
        if not text:
            return ''
        # 常见转义
        replacements = [
            ('&nbsp;', ' '),
            ('&amp;', '&'),
            ('&lt;', '<'),
            ('&gt;', '>'),
            ('&quot;', '"'),
            ('&#39;', "'"),
            ('\\n', '\n'),
            ('\\r', '\r'),
            ('\\t', '\t'),
            ('\\', ''),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    @staticmethod
    def format_paragraphs(text: str) -> str:
        """格式化段落"""
        if not text:
            return ''

        # 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 移除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]

        # 合并过多的空行（超过 2 个空行压缩为 1 个）
        result_lines = []
        empty_count = 0
        for line in lines:
            if not line:
                empty_count += 1
                if empty_count <= 1:
                    result_lines.append('')
            else:
                empty_count = 0
                result_lines.append(line)

        # 去掉首尾空行
        while result_lines and not result_lines[0]:
            result_lines.pop(0)
        while result_lines and not result_lines[-1]:
            result_lines.pop()

        return '\n'.join(result_lines)

    @classmethod
    def remove_ads(cls, text: str, extra_patterns: List[str] = None) -> str:
        """去广告"""
        if not text:
            return ''

        patterns = cls.DEFAULT_AD_PATTERNS + (extra_patterns or [])
        result = text
        for pattern in patterns:
            try:
                result = re.sub(pattern, '', result)
            except re.error:
                continue
        return result

    @classmethod
    def extract_chapter_title(cls, text: str) -> Optional[str]:
        """从文本开头提取章节标题"""
        if not text:
            return None

        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if not lines:
            return None

        first_line = lines[0]
        for pattern in cls.CHAPTER_TITLE_PATTERNS:
            if re.match(pattern, first_line):
                return first_line

        return None

    @classmethod
    def clean_content(cls, content: str, replace_rule: Any = None) -> str:
        """
        完整的正文内容清洗

        Args:
            content: 原始内容
            replace_rule: 替换规则配置

        Returns:
            清洗后的内容
        """
        if not content:
            return ''

        pipeline = cls()

        # 加载自定义替换规则
        if replace_rule:
            pipeline.add_rules_from_config(replace_rule)

        # 执行处理
        result = pipeline.process(content)

        # 去广告
        result = cls.remove_ads(result)

        # 再次格式化
        result = cls.format_paragraphs(result)

        return result

    @staticmethod
    def text_similarity(a: str, b: str) -> float:
        """
        计算两段文本的相似度（0-1）

        基于字符级 2-gram Jaccard 相似度 + 句子重叠
        """
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        # 去空白后比较
        a_clean = re.sub(r'\s+', '', a)
        b_clean = re.sub(r'\s+', '', b)

        if not a_clean or not b_clean:
            return 0.0

        # 2-gram Jaccard
        def get_ngrams(text, n=2):
            if len(text) < n:
                return set(text)
            return set(text[i:i + n] for i in range(len(text) - n + 1))

        set_a = get_ngrams(a_clean)
        set_b = get_ngrams(b_clean)

        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        jaccard = intersection / union if union > 0 else 0.0

        # 长度比例
        len_ratio = min(len(a_clean), len(b_clean)) / max(len(a_clean), len(b_clean))

        return jaccard * 0.7 + len_ratio * 0.3

    @staticmethod
    def word_count(text: str) -> int:
        """计算正文字数（去除空白和标点）"""
        if not text:
            return 0
        # 移除空白
        clean = re.sub(r'\s+', '', text)
        # 移除常见标点
        clean = re.sub(r"[，。！？、；：\"'（）《》【】…—\-\.,!?;]", "", clean)
        return len(clean)
