"""
问答技能 - QA Skill

负责：
- 情节搜索
- 章节摘要
- 人物时间线
- 社区查询
- 智能问答
"""

import re
from typing import List, Dict, Any
from collections import defaultdict
from ..registry import BaseSkill, ToolDefinition


class QASkill(BaseSkill):
    name = 'qa'

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='plot_search',
                description='搜索小说中的情节片段',
                parameters={
                    'keyword': {'type': 'string', 'required': True, 'desc': '搜索关键词'},
                    'limit': {'type': 'int', 'default': 5, 'desc': '最大结果数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='chapter_summary',
                description='获取章节摘要',
                parameters={
                    'chapter_num': {'type': 'int', 'required': True, 'desc': '章节号'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='character_timeline',
                description='获取人物出场时间线',
                parameters={
                    'char_name': {'type': 'string', 'required': True, 'desc': '人物名称'},
                    'limit': {'type': 'int', 'default': 10, 'desc': '返回数量'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='answer_question',
                description='基于原文回答问题',
                parameters={
                    'question': {'type': 'string', 'required': True, 'desc': '问题'},
                    'context_chars': {'type': 'int', 'default': 200, 'desc': '上下文窗口'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='compare_characters',
                description='对比两个人物的关系和互动',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'plot_search':
            return self._plot_search(params.get('keyword', ''), params.get('limit', 5))
        elif tool_name == 'chapter_summary':
            return self._chapter_summary(params.get('chapter_num', 1))
        elif tool_name == 'character_timeline':
            return self._char_timeline(params.get('char_name', ''), params.get('limit', 10))
        elif tool_name == 'answer_question':
            return self._answer(params.get('question', ''), params.get('context_chars', 200))
        elif tool_name == 'compare_characters':
            return self._compare(params.get('char1', ''), params.get('char2', ''))
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _plot_search(self, keyword: str, limit: int) -> Dict:
        if not self.store or not keyword:
            return {'tool': 'plot_search', 'results': [], 'total': 0}

        results = self.store.search_text(keyword, limit)
        return {
            'tool': 'plot_search',
            'keyword': keyword,
            'results': results,
            'total': len(results),
        }

    def _chapter_summary(self, chapter_num: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'chapter_summary'}

        ch = self.store.get_chapter(chapter_num - 1)
        if not ch:
            return {
                'tool': 'chapter_summary',
                'found': False,
                'chapter': chapter_num,
                'total_chapters': len(self.store.chapters),
            }

        content = ch.content
        present_chars = [c for c in self.store.all_chars if c in content]
        key_sentences = []
        for sent in re.split(r'[。！？\n]', content):
            if any(c in sent for c in present_chars) and len(sent) > 10:
                key_sentences.append(sent.strip()[:150])
                if len(key_sentences) >= 8:
                    break

        return {
            'tool': 'chapter_summary',
            'found': True,
            'chapter': chapter_num,
            'title': ch.title,
            'content_length': len(content),
            'characters_present': present_chars[:15],
            'character_count': len(present_chars),
            'key_sentences': key_sentences[:5],
        }

    def _char_timeline(self, char_name: str, limit: int) -> Dict:
        if not self.store:
            return {'tool': 'character_timeline', 'timeline': []}

        positions = self.store.char_index.get(char_name, [])
        ch_appear = defaultdict(list)
        for ci, pos in positions:
            ch_appear[ci].append(pos)

        sorted_chs = sorted(ch_appear.items(), key=lambda x: x[0])
        if len(sorted_chs) > limit:
            step = len(sorted_chs) // limit
            sampled = sorted_chs[::step][:limit]
        else:
            sampled = sorted_chs

        timeline = []
        for ci, plist in sampled:
            ch = self.store.get_chapter(ci)
            if not ch:
                continue
            content = ch.content
            first_pos = plist[0]
            ctx = content[max(0, first_pos - 50):first_pos + 100].replace('\n', ' ').strip()
            timeline.append({
                'chapter_idx': ci,
                'chapter': ch.chapter,
                'title': ch.title,
                'appearance_count': len(plist),
                'first_context': ctx[:200],
            })

        return {
            'tool': 'character_timeline',
            'character': char_name,
            'total_chapters': len(ch_appear),
            'total_occurrences': len(positions),
            'timeline': timeline,
            'sampled': len(timeline),
        }

    def _answer(self, question: str, context_chars: int) -> Dict:
        if not self.store or not question:
            return {'tool': 'answer_question', 'answer': '', 'evidence': []}

        q_words = [w for w in re.findall(r'[\u4e00-\u9fff]{2,}', question) if len(w) >= 2]
        if not q_words:
            q_words = list(question)

        char_in_question = [c for c in self.store.all_chars if c in question]

        evidence = []
        scored_sents = []

        for ch in self.store.chapters:
            content = ch.content
            if char_in_question:
                has_char = any(c in content for c in char_in_question)
                if not has_char:
                    continue
            for sent in re.split(r'[。！？\n]', content):
                if len(sent) < 10:
                    continue
                score = sum(1 for w in q_words if w in sent)
                if score > 0:
                    scored_sents.append({
                        'sentence': sent.strip()[:200],
                        'score': score,
                        'chapter': ch.chapter,
                        'title': ch.title,
                    })

        scored_sents.sort(key=lambda x: -x['score'])
        evidence = scored_sents[:5]

        answer = ''
        if evidence:
            answer = evidence[0]['sentence']
            if len(evidence) > 1:
                answer += '\n\n相关内容：\n' + '\n'.join(
                    f"- [{e['chapter']}] {e['sentence'][:100]}..." for e in evidence[1:3]
                )

        return {
            'tool': 'answer_question',
            'question': question,
            'answer': answer,
            'evidence': evidence,
            'evidence_count': len(evidence),
            'confidence': min(1.0, len(evidence) / 5) if evidence else 0,
        }

    def _compare(self, c1: str, c2: str) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'compare_characters'}

        pair = tuple(sorted([c1, c2]))
        co_chapters = len(self.store.char_pair_index.get(pair, []))

        rel = self.store.get_relation(c1, c2)
        info1 = self.store.get_community(c1)
        info2 = self.store.get_community(c2)

        interactions = []
        sents = self.store.get_sentences(c1, c2, limit=10)
        for s in sents:
            interactions.append({
                'chapter': s.get('chapter', ''),
                'sentence': s.get('sentence', '')[:150],
            })

        return {
            'tool': 'compare_characters',
            'char1': c1,
            'char2': c2,
            'co_occurrence_chapters': co_chapters,
            'relation_type': rel.get('type') if rel else 'unknown',
            'relation_description': rel.get('description', '') if rel else '',
            'confidence': rel.get('confidence', 0) if rel else 0,
            'same_community': info1.get('name') == info2.get('name') if info1 and info2 else False,
            'community_1': info1.get('name', '未知') if info1 else '未知',
            'community_2': info2.get('name', '未知') if info2 else '未知',
            'interactions': interactions,
            'interaction_count': len(interactions),
        }
