"""
小说数据存储层 - 统一的数据访问接口

负责：
- 章节数据加载与索引
- 关系图谱数据管理
- 人物实体索引
- 全文检索支持
"""

import json
import re
import glob
import os
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field


class NovelDataStoreError(ValueError):
    """Raised when configured novel data cannot be loaded safely."""


@dataclass
class ChapterData:
    chapter: str = ''
    title: str = ''
    content: str = ''
    index: int = 0


@dataclass
class NovelDataStore:
    """小说数据存储

    索引结构：
    - char_index: 人物名 -> [(章节索引, 位置), ...]
    - char_pair_index: (人物1, 人物2) -> [章节索引, ...]
    - chapter_index: 章节索引 -> ChapterData
    """

    config: Optional[dict] = None
    chapters: List[ChapterData] = field(default_factory=list)
    graph: Dict = field(default_factory=dict)
    all_chars: set = field(default_factory=set)
    char_index: Dict[str, List[Tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))
    char_pair_index: Dict[Tuple[str, str], List[int]] = field(default_factory=lambda: defaultdict(list))
    full_text: str = ''

    def __post_init__(self):
        if self.config:
            self._load_from_config()

    def _load_from_config(self):
        data_dir = self.config.get('novel.data_dir', 'data/novels')
        novel_name = self.config.get('novel.name', '')

        os.makedirs(data_dir, exist_ok=True)

        pattern = os.path.join(data_dir, f'{novel_name}_*.json' if novel_name else '*.json')
        for f in sorted(glob.glob(pattern)):
            basename = os.path.basename(f).lower()
            if any(x in basename for x in [
                'analysis', 'final', 'smart', 'graph', 'mcp',
                'validation', 'toolkit', 'audit', 'engine',
            ]):
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise NovelDataStoreError(f'failed to load chapter data {f}: {exc}') from exc

            if not isinstance(data, list):
                raise NovelDataStoreError(f'chapter data file {f} must contain a JSON array')
            for i, ch in enumerate(data):
                if not isinstance(ch, dict):
                    raise NovelDataStoreError(
                        f'chapter data file {f} contains a non-object chapter at index {i}'
                    )
                self.chapters.append(ChapterData(
                    chapter=str(ch.get('chapter', i+1)),
                    title=ch.get('title', f'第{i+1}章'),
                    content=ch.get('content', ''),
                    index=len(self.chapters),
                ))

        graph_file = self.config.get('novel.graph_file', 'data/graph.json')
        try:
            with open(graph_file, 'r', encoding='utf-8') as f:
                self.graph = json.load(f)
        except FileNotFoundError:
            self.graph = {'relations': [], 'communities': []}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise NovelDataStoreError(f'failed to load graph data {graph_file}: {exc}') from exc

        if not isinstance(self.graph, dict):
            raise NovelDataStoreError(f'graph data file {graph_file} must contain a JSON object')

        for ci in self.graph.get('communities', []):
            if not isinstance(ci, dict):
                raise NovelDataStoreError(
                    f'graph data file {graph_file} contains a non-object community'
                )
            self.all_chars.update(ci.get('members', []))

        self._build_indexes()

    def _build_indexes(self):
        for ch in self.chapters:
            content = ch.content
            for char in self.all_chars:
                pos = 0
                while True:
                    p = content.find(char, pos)
                    if p == -1:
                        break
                    self.char_index[char].append((ch.index, p))
                    pos = p + 1

            present = [c for c in self.all_chars if c in content]
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    pair = tuple(sorted([present[i], present[j]]))
                    self.char_pair_index[pair].append(ch.index)

        self.full_text = '\n'.join(ch.content for ch in self.chapters)

    def load_from_json(self, chapters_data: List[Dict], graph_data: Optional[Dict] = None):
        """从内存数据加载（用于 API 调用）"""
        self.chapters = []
        for i, ch in enumerate(chapters_data):
            self.chapters.append(ChapterData(
                chapter=str(ch.get('chapter', i + 1)),
                title=ch.get('title', f'第{i + 1}章'),
                content=ch.get('content', ''),
                index=i,
            ))

        if graph_data:
            self.graph = graph_data
            self.all_chars = set()
            for ci in self.graph.get('communities', []):
                self.all_chars.update(ci.get('members', []))

        self._build_indexes()

    def get_sentences(self, c1: str, c2: Optional[str] = None, limit: int = 10) -> List[Dict]:
        results = []
        for ch in self.chapters:
            content = ch.content
            if c1 not in content:
                continue
            if c2 and c2 not in content:
                continue
            for sent in re.split(r'[。！？\n]', content):
                if c1 in sent and (c2 is None or c2 in sent):
                    results.append({
                        'chapter': ch.chapter,
                        'chapter_idx': ch.index,
                        'title': ch.title,
                        'sentence': sent.strip(),
                    })
                    if len(results) >= limit:
                        return results
        return results

    def get_character_occurrences(self, char_name: str) -> int:
        return len(self.char_index.get(char_name, []))

    def get_relation(self, c1: str, c2: str) -> Optional[Dict]:
        for r in self.graph.get('relations', []):
            if (r.get('char1') == c1 and r.get('char2') == c2) or \
               (r.get('char1') == c2 and r.get('char2') == c1):
                return r
        return None

    def get_community(self, char_name: str) -> Optional[Dict]:
        for ci in self.graph.get('communities', []):
            if char_name in ci.get('members', []):
                return ci
        return None

    def search_text(self, keyword: str, limit: int = 10) -> List[Dict]:
        results = []
        for ch in self.chapters:
            content = ch.content
            if keyword in content:
                pos = content.find(keyword)
                ctx = content[max(0, pos - 100):pos + 200].replace('\n', ' ').strip()
                results.append({
                    'chapter': ch.chapter,
                    'title': ch.title,
                    'position': pos,
                    'context': ctx[:300],
                })
                if len(results) >= limit:
                    break
        return results

    def get_chapter(self, idx: int) -> Optional[ChapterData]:
        if 0 <= idx < len(self.chapters):
            return self.chapters[idx]
        return None

    def stats(self) -> Dict:
        rels = self.graph.get('relations', [])
        comms = self.graph.get('communities', [])
        type_counts = Counter(r.get('type', 'unknown') for r in rels)
        return {
            'chapters': len(self.chapters),
            'characters': len(self.all_chars),
            'relations': len(rels),
            'communities': len(comms),
            'relation_types': dict(type_counts),
            'total_chars': len(self.full_text),
        }
