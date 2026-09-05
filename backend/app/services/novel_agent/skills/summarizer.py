"""
总结技能 - Summarizer Skill

负责：
- 全书概要
- 章节摘要
- 人物简介
- 剧情梗概
- 主题分析
"""

import re
from typing import List, Dict, Any
from collections import defaultdict, Counter
from ..registry import BaseSkill, ToolDefinition


class SummarizerSkill(BaseSkill):
    name = 'summarizer'

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='book_overview',
                description='生成全书概要',
                parameters={
                    'max_length': {'type': 'int', 'default': 1000, 'desc': '最大长度'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='range_summary',
                description='生成指定章节范围的摘要',
                parameters={
                    'start_chapter': {'type': 'int', 'required': True, 'desc': '起始章节'},
                    'end_chapter': {'type': 'int', 'required': True, 'desc': '结束章节'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='character_profile',
                description='生成人物简介',
                parameters={
                    'char_name': {'type': 'string', 'required': True, 'desc': '人物名称'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='plot_outline',
                description='生成剧情大纲',
                parameters={
                    'parts': {'type': 'int', 'default': 5, 'desc': '划分部分数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='theme_analysis',
                description='主题分析',
                parameters={
                    'top_n': {'type': 'int', 'default': 10, 'desc': '前N个主题'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'book_overview':
            return self._book_overview(params.get('max_length', 1000))
        elif tool_name == 'range_summary':
            return self._range_summary(
                params.get('start_chapter', 1),
                params.get('end_chapter', 10),
            )
        elif tool_name == 'character_profile':
            return self._char_profile(params.get('char_name', ''))
        elif tool_name == 'plot_outline':
            return self._plot_outline(params.get('parts', 5))
        elif tool_name == 'theme_analysis':
            return self._theme_analysis(params.get('top_n', 10))
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _book_overview(self, max_length: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'book_overview'}

        stats = self.store.stats()
        top_chars = sorted(
            [(c, len(self.store.char_index.get(c, []))) for c in self.store.all_chars],
            key=lambda x: -x[1]
        )[:10]

        comms = []
        for ci in self.store.graph.get('communities', []):
            comms.append({
                'name': ci.get('name', ''),
                'size': len(ci.get('members', [])),
                'members': ci.get('members', [])[:5],
            })

        overview = f"""本书共 {stats['chapters']} 章，约 {stats['total_chars']:,} 字。

主要人物（{len(self.store.all_chars)}人）：
{', '.join(f"{c}({n}次)" for c, n in top_chars[:5])}

主要阵营（{len(comms)}个）：
{', '.join(f"{c['name']}({c['size']}人)" for c in comms)}

人物关系共 {stats['relations']} 条，涵盖 {len(stats['relation_types'])} 种类型。
"""

        return {
            'tool': 'book_overview',
            'overview': overview[:max_length],
            'stats': stats,
            'top_characters': [{'name': c, 'occurrences': n} for c, n in top_chars],
            'communities': comms,
        }

    def _range_summary(self, start: int, end: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'range_summary'}

        start_idx = max(0, start - 1)
        end_idx = min(len(self.store.chapters), end)

        chapters_summary = []
        all_chars_in_range = set()
        key_events = []

        for i in range(start_idx, end_idx):
            ch = self.store.get_chapter(i)
            if not ch:
                continue
            content = ch.content
            present = [c for c in self.store.all_chars if c in content]
            all_chars_in_range.update(present)

            key_sent = ''
            for sent in re.split(r'[。！？\n]', content):
                if any(c in sent for c in present) and len(sent) > 15:
                    key_sent = sent.strip()[:100]
                    break

            chapters_summary.append({
                'chapter': ch.chapter,
                'title': ch.title,
                'characters': present[:8],
                'key_sentence': key_sent,
            })

            if key_sent and len(key_events) < 20:
                key_events.append({
                    'chapter': ch.chapter,
                    'event': key_sent,
                })

        return {
            'tool': 'range_summary',
            'start_chapter': start,
            'end_chapter': end_idx,
            'chapter_count': end_idx - start_idx,
            'chapters': chapters_summary,
            'characters_involved': list(all_chars_in_range)[:20],
            'character_count': len(all_chars_in_range),
            'key_events': key_events[:10],
        }

    def _char_profile(self, char_name: str) -> Dict:
        if not self.store or char_name not in self.store.all_chars:
            return {'tool': 'character_profile', 'found': False, 'name': char_name}

        occurrences = self.store.get_character_occurrences(char_name)
        comm = self.store.get_community(char_name)

        rels = []
        for r in self.store.graph.get('relations', []):
            other = r['char2'] if r['char1'] == char_name else (r['char1'] if r['char2'] == char_name else None)
            if other:
                rels.append({
                    'character': other,
                    'type': r.get('type', ''),
                    'description': r.get('description', ''),
                    'confidence': r.get('confidence', 0.5),
                })

        first_chapter = None
        last_chapter = None
        positions = self.store.char_index.get(char_name, [])
        if positions:
            first_ci = positions[0][0]
            last_ci = positions[-1][0]
            first_ch = self.store.get_chapter(first_ci)
            last_ch = self.store.get_chapter(last_ci)
            first_chapter = first_ch.chapter if first_ch else None
            last_chapter = last_ch.chapter if last_ch else None

        profile = f"""{char_name}
出场次数: {occurrences}次
所属阵营: {comm.get('name', '未知') if comm else '未知'}
首次出场: 第{first_chapter}章
最后出场: 第{last_chapter}章
关系数: {len(rels)}条
主要关系:
"""
        for r in sorted(rels, key=lambda x: -x['confidence'])[:5]:
            profile += f"  - {r['character']} ({r['type']}): {r['description'] or '无描述'}\n"

        return {
            'tool': 'character_profile',
            'found': True,
            'name': char_name,
            'profile': profile,
            'occurrences': occurrences,
            'community': comm.get('name') if comm else '未知',
            'first_chapter': first_chapter,
            'last_chapter': last_chapter,
            'relations': sorted(rels, key=lambda x: -x['confidence']),
            'relation_count': len(rels),
        }

    def _plot_outline(self, parts: int) -> Dict:
        if not self.store or not self.store.chapters:
            return {'tool': 'plot_outline', 'parts': []}

        total = len(self.store.chapters)
        part_size = max(1, total // parts)
        part_list = []

        for i in range(parts):
            start = i * part_size
            end = min(total, (i + 1) * part_size) if i < parts - 1 else total

            part_chars = set()
            key_event = ''
            for ci in range(start, end):
                ch = self.store.get_chapter(ci)
                if not ch:
                    continue
                present = [c for c in self.store.all_chars if c in ch.content]
                part_chars.update(present)

                if not key_event:
                    for sent in re.split(r'[。！？\n]', ch.content):
                        if any(c in sent for c in present) and len(sent) > 15:
                            key_event = sent.strip()[:100]
                            break

            part_list.append({
                'part': i + 1,
                'start_chapter': start + 1,
                'end_chapter': end,
                'chapter_count': end - start,
                'main_characters': list(part_chars)[:8],
                'key_event': key_event,
            })

        return {
            'tool': 'plot_outline',
            'total_chapters': total,
            'parts_count': len(part_list),
            'parts': part_list,
        }

    def _theme_analysis(self, top_n: int) -> Dict:
        if not self.store:
            return {'tool': 'theme_analysis', 'themes': []}

        theme_keywords = {
            '冒险': ['冒险', '探险', '探索', '秘境', '古墓', '宝藏'],
            '悬疑': ['悬疑', '谜团', '真相', '秘密', '诡异', '离奇'],
            '情感': ['爱情', '亲情', '友情', '兄弟', '守护', '牺牲'],
            '成长': ['成长', '变强', '修炼', '突破', '觉醒', '领悟'],
            '正邪': ['正义', '邪恶', '正邪', '阴谋', '反派', '正道'],
            '灵异': ['灵异', '鬼怪', '僵尸', '鬼魂', '阴气', '尸'],
            '友情': ['朋友', '兄弟', '伙伴', '队友', '并肩', '托付'],
            '复仇': ['复仇', '报仇', '仇恨', '血债', '报复'],
            '宿命': ['命运', '宿命', '天命', '轮回', '前世', '注定'],
            '守护': ['守护', '保护', '庇佑', '守卫', '护着'],
        }

        theme_scores = defaultdict(int)
        full_text = self.store.full_text[:50000]

        for theme, keywords in theme_keywords.items():
            for kw in keywords:
                theme_scores[theme] += full_text.count(kw)

        sorted_themes = sorted(theme_scores.items(), key=lambda x: -x[1])[:top_n]
        total = sum(v for _, v in sorted_themes) or 1

        themes = []
        for name, score in sorted_themes:
            themes.append({
                'theme': name,
                'score': score,
                'percentage': round(score / total * 100, 1),
                'keywords': theme_keywords.get(name, []),
            })

        return {
            'tool': 'theme_analysis',
            'themes': themes,
            'top_n': len(themes),
            'total_score': total,
        }
