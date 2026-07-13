"""
抽取技能 - Extractor Skill

负责：
- 人物实体抽取
- 关系抽取
- 别名识别
- 实体属性提取
"""

import re
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict, Counter
from ..registry import BaseSkill, ToolDefinition


class ExtractorSkill(BaseSkill):
    name = 'extractor'

    COMMON_SURNAMES = set([
        '赵', '钱', '孙', '李', '周', '吴', '郑', '王', '冯', '陈', '褚', '卫',
        '蒋', '沈', '韩', '杨', '朱', '秦', '尤', '许', '何', '吕', '施', '张',
        '孔', '曹', '严', '华', '金', '魏', '陶', '姜', '戚', '谢', '邹', '喻',
        '柏', '水', '窦', '章', '云', '苏', '潘', '葛', '奚', '范', '彭', '郎',
        '柳', '薛', '雷', '贺', '倪', '汤', '滕', '殷', '罗', '毕', '郝', '邬',
        '林', '刁', '钟', '徐', '邱', '骆', '高', '夏', '蔡', '田', '樊', '胡',
    ])

    RELATION_PATTERNS = {
        'family': [
            r'([\u4e00-\u9fff]{2,4})的(爷爷|奶奶|爸爸|妈妈|爹|娘|叔|伯|儿子|女儿|孙子|孙女)',
        ],
        'romance': [
            r'([\u4e00-\u9fff]{2,4})和([\u4e00-\u9fff]{2,4})(结婚|恋爱|在一起)',
        ],
        'friend': [
            r'([\u4e00-\u9fff]{2,4})和([\u4e00-\u9fff]{2,4})(是|做了)(闺蜜|好友|兄弟)',
        ],
        'master': [
            r'([\u4e00-\u9fff]{2,4})(*)(为师|为师|学艺|为师)',
        ],
        'guardian': [
            r'([\u4e00-\u9fff]{2,4})的(守护灵|灵兽|守护)',
        ],
    }

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='extract_characters',
                description='从文本中抽取人物实体',
                parameters={
                    'text': {'type': 'string', 'desc': '待分析文本'},
                    'chapter_range': {'type': 'string', 'desc': '章节范围，如 1-50'},
                    'min_occurrences': {'type': 'int', 'default': 2, 'desc': '最少出现次数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='extract_relations',
                description='抽取人物之间的关系',
                parameters={
                    'char1': {'type': 'string', 'desc': '人物1'},
                    'char2': {'type': 'string', 'desc': '人物2'},
                    'relation_type': {'type': 'string', 'desc': '关系类型过滤'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='extract_aliases',
                description='识别人物别名',
                parameters={
                    'char_name': {'type': 'string', 'desc': '人物名称'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='recall_context',
                description='召回人物的上下文语境',
                parameters={
                    'char_name': {'type': 'string', 'required': True, 'desc': '人物名字'},
                    'window': {'type': 'int', 'default': 200, 'desc': '上下文窗口大小'},
                    'limit': {'type': 'int', 'default': 5, 'desc': '返回数量'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='search_pattern',
                description='搜索原文中的关系句式模式',
                parameters={
                    'pattern_type': {'type': 'string', 'required': True, 'desc': '模式类型: family/spouse/romance/friend/master/guardian'},
                    'limit': {'type': 'int', 'default': 5, 'desc': '最大结果数'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'extract_characters':
            return self._extract_chars(params)
        elif tool_name == 'extract_relations':
            return self._extract_relations(params)
        elif tool_name == 'extract_aliases':
            return self._extract_aliases(params.get('char_name', ''))
        elif tool_name == 'recall_context':
            return self._recall_context(
                params.get('char_name', ''),
                params.get('window', 200),
                params.get('limit', 5),
            )
        elif tool_name == 'search_pattern':
            return self._search_pattern(
                params.get('pattern_type', ''),
                params.get('limit', 5),
            )
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _extract_chars(self, params: Dict) -> Dict:
        if not self.store:
            return {'tool': 'extract_characters', 'characters': [], 'total': 0}

        min_occ = params.get('min_occurrences', 2)
        chars = []
        for c in sorted(self.store.all_chars):
            occ = self.store.get_character_occurrences(c)
            if occ >= min_occ:
                comm = self.store.get_community(c)
                chars.append({
                    'name': c,
                    'occurrences': occ,
                    'community': comm.get('name') if comm else '未知',
                })

        return {
            'tool': 'extract_characters',
            'characters': sorted(chars, key=lambda x: -x['occurrences']),
            'total': len(chars),
            'min_occurrences': min_occ,
        }

    def _extract_relations(self, params: Dict) -> Dict:
        if not self.store:
            return {'tool': 'extract_relations', 'relations': [], 'total': 0}

        c1 = params.get('char1', '')
        c2 = params.get('char2', '')
        rtype = params.get('relation_type', '')

        rels = []
        for r in self.store.graph.get('relations', []):
            if c1 and c2:
                if not ((r['char1'] == c1 and r['char2'] == c2) or
                        (r['char1'] == c2 and r['char2'] == c1)):
                    continue
            elif c1:
                if r['char1'] != c1 and r['char2'] != c1:
                    continue
            if rtype and r.get('type') != rtype:
                continue
            rels.append(r)

        return {
            'tool': 'extract_relations',
            'relations': rels,
            'total': len(rels),
            'filter': {'char1': c1, 'char2': c2, 'type': rtype},
        }

    def _extract_aliases(self, char_name: str) -> Dict:
        if not self.store or not char_name:
            return {'tool': 'extract_aliases', 'aliases': []}

        aliases = []
        for ch in self.store.chapters[:20]:
            content = ch.content
            if char_name not in content:
                continue
            for m in re.finditer(rf'{char_name}（([^）]+)）', content):
                alias = m.group(1)
                if 2 <= len(alias) <= 4:
                    aliases.append(alias)

        alias_counts = Counter(aliases)
        result = [
            {'alias': a, 'count': c, 'confidence': min(1.0, c / 10)}
            for a, c in alias_counts.most_common(10)
        ]

        return {
            'tool': 'extract_aliases',
            'character': char_name,
            'aliases': result,
            'total': len(result),
        }

    def _recall_context(self, char_name: str, window: int, limit: int) -> Dict:
        if not self.store:
            return {'tool': 'recall_context', 'contexts': [], 'total': 0}

        positions = self.store.char_index.get(char_name, [])
        ctxs = []

        if len(positions) > limit:
            step = len(positions) // limit
            sampled = positions[::step][:limit]
        else:
            sampled = positions[:limit]

        for ci, pos in sampled:
            ch = self.store.get_chapter(ci)
            if not ch:
                continue
            content = ch.content
            s, e = max(0, pos - window), min(len(content), pos + window)
            ctx = re.sub(r'\s+', ' ', content[s:e]).strip()
            ctxs.append({
                'chapter_idx': ci,
                'chapter': ch.chapter,
                'title': ch.title,
                'position': pos,
                'context': ctx[:400],
            })

        return {
            'tool': 'recall_context',
            'character': char_name,
            'total_occurrences': len(positions),
            'contexts': ctxs,
            'sampled': len(ctxs),
        }

    def _search_pattern(self, pattern_type: str, limit: int) -> Dict:
        if not self.store:
            return {'tool': 'search_pattern', 'results': [], 'total': 0}

        PATTERN_MAP = {
            'family': r'([\u4e00-\u9fff]{2,4})(?:的)(爷爷|奶奶|爸爸|妈妈|爹|娘|叔|伯|儿子|女儿|孙子|孙女)',
            'spouse': r'([\u4e00-\u9fff]{2,4})(?:嫁给|娶了|嫁了)([\u4e00-\u9fff]{2,4})',
            'romance': r'([\u4e00-\u9fff]{2,4})(?:和|与)([\u4e00-\u9fff]{2,4})(?:结婚|恋爱|在一起)',
            'friend': r'([\u4e00-\u9fff]{2,4})(?:和|与)([\u4e00-\u9fff]{2,4})(?:是|做了)(?:闺蜜|好友|兄弟)',
            'master': r'([\u4e00-\u9fff]{2,4})(?:拜|认|跟着)([\u4e00-\u9fff]{2,4})(?:为师|学艺|学武)',
            'teach': r'([\u4e00-\u9fff]{2,4})(?:教|传授|教导)([\u4e00-\u9fff]{2,4})',
            'guardian': r'([\u4e00-\u9fff]{2,4})的(守护灵|灵兽|守护)',
        }

        regex = PATTERN_MAP.get(pattern_type, pattern_type)
        results = []

        for ch in self.store.chapters:
            content = ch.content
            for m in re.finditer(regex, content):
                s, e = max(0, m.start() - 30), min(len(content), m.end() + 50)
                ctx = content[s:e].replace('\n', ' ').strip()
                groups = m.groups()
                known_chars = [g for g in groups if g and g in self.store.all_chars]
                results.append({
                    'match': m.group()[:60],
                    'context': ctx[:150],
                    'groups': list(groups),
                    'known_chars': known_chars,
                    'chapter': ch.chapter,
                    'title': ch.title,
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        return {
            'tool': 'search_pattern',
            'pattern_type': pattern_type,
            'regex': regex if pattern_type in PATTERN_MAP else 'custom',
            'results': results,
            'total': len(results),
        }
