"""
推理技能 - Reasoner Skill

负责：
- 关系推理
- 剧情推演
- 伏笔分析
- 结局预测
- 逻辑验证
"""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from ..registry import BaseSkill, ToolDefinition


class ReasonerSkill(BaseSkill):
    name = 'reasoner'

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='infer_relation',
                description='推理两人之间的关系类型',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                    'method': {'type': 'string', 'default': 'hybrid', 'desc': '推理方法: evidence/community/hybrid'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='plot_prediction',
                description='基于已有情节预测后续发展',
                parameters={
                    'current_chapter': {'type': 'int', 'desc': '当前章节'},
                    'foresight_steps': {'type': 'int', 'default': 3, 'desc': '预测步数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='foreshadow_analysis',
                description='分析文中伏笔和暗示',
                parameters={
                    'keyword': {'type': 'string', 'desc': '伏笔关键词'},
                    'limit': {'type': 'int', 'default': 10, 'desc': '最大结果数'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='ending_analysis',
                description='分析可能的结局走向',
                parameters={
                    'ending_types': {'type': 'int', 'default': 3, 'desc': '结局类型数量'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='logic_check',
                description='检查剧情逻辑一致性',
                parameters={
                    'char_name': {'type': 'string', 'desc': '指定人物'},
                    'detail_level': {'type': 'string', 'default': 'medium', 'desc': '详细程度'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='extract_evidence',
                description='提取两人关系的原文证据',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                    'limit': {'type': 'int', 'default': 5, 'desc': '每种证据最大数量'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'infer_relation':
            return self._infer_relation(
                params.get('char1', ''),
                params.get('char2', ''),
                params.get('method', 'hybrid'),
            )
        elif tool_name == 'plot_prediction':
            return self._plot_prediction(
                params.get('current_chapter', 0),
                params.get('foresight_steps', 3),
            )
        elif tool_name == 'foreshadow_analysis':
            return self._foreshadow(
                params.get('keyword', ''),
                params.get('limit', 10),
            )
        elif tool_name == 'ending_analysis':
            return self._ending_analysis(params.get('ending_types', 3))
        elif tool_name == 'logic_check':
            return self._logic_check(
                params.get('char_name', ''),
                params.get('detail_level', 'medium'),
            )
        elif tool_name == 'extract_evidence':
            return self._extract_evidence(
                params.get('char1', ''),
                params.get('char2', ''),
                params.get('limit', 5),
            )
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _infer_relation(self, c1: str, c2: str, method: str) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'infer_relation'}

        scores = defaultdict(float)
        evidence = {'dialogue': [], 'address': [], 'action': [], 'proximity': []}

        pair = tuple(sorted([c1, c2]))
        co_count = len(self.store.char_pair_index.get(pair, []))

        sents = self.store.get_sentences(c1, c2, limit=30)
        for s in sents:
            sent = s['sentence']

            if '：「' in sent or '」' in sent:
                if len(evidence['dialogue']) < 5:
                    evidence['dialogue'].append({'text': sent[:200]})

            for t in ['爷爷', '奶奶', '爹', '娘', '爸爸', '妈妈', '叔', '婶', '姨',
                      '师傅', '师父', '哥', '姐', '妹', '夫妻', '闺蜜', '结婚', '嫁', '娶']:
                if t in sent and (c1 + t in sent or t + c1 in sent or c2 + t in sent or t + c2 in sent):
                    if t in ['爷爷', '奶奶', '爹', '娘', '爸爸', '妈妈', '儿子', '女儿']:
                        scores['family'] += 3
                    elif t in ['师傅', '师父']:
                        scores['master'] += 3
                    elif t in ['闺蜜', '兄弟', '好友']:
                        scores['friend'] += 3
                    elif t in ['夫妻', '嫁', '娶']:
                        scores['family'] += 3
                    elif t in ['结婚', '恋爱']:
                        scores['romance'] += 3
                    if len(evidence['address']) < 5:
                        evidence['address'].append({'term': t, 'text': sent[:200]})
                    break

            for a in ['教', '传授', '保护', '守护', '救', '一起', '帮忙', '送', '背', '住']:
                if a in sent:
                    if a in ['教', '传授']:
                        scores['master'] += 2
                    elif a in ['保护', '守护', '救']:
                        scores['guardian'] += 2
                    elif a in ['一起', '帮忙', '送', '背']:
                        scores['companion'] += 1
                    elif a in ['住']:
                        scores['family'] += 1
                    if len(evidence['action']) < 5:
                        evidence['action'].append({'action': a, 'text': sent[:200]})
                    break

            p1, p2 = sent.find(c1), sent.find(c2)
            if p1 != -1 and p2 != -1 and abs(p1 - p2) < 30:
                scores['companion'] += 0.5
                if len(evidence['proximity']) < 5:
                    evidence['proximity'].append({'distance': abs(p1 - p2), 'text': sent[:200]})

        comm1 = self.store.get_community(c1)
        comm2 = self.store.get_community(c2)
        if comm1 and comm2 and comm1.get('name') == comm2.get('name'):
            scores['companion'] += 1

        total_score = sum(scores.values())
        if total_score > 0:
            normalized = {k: round(v / total_score, 3) for k, v in scores.items()}
            best_type = max(normalized, key=normalized.get)
            confidence = normalized[best_type]
        else:
            normalized = {}
            best_type = 'companion'
            confidence = 0.3

        reasoning_chain = [
            {'step': 1, 'type': 'co_occurrence', 'desc': f'共现章节: {co_count}章'},
            {'step': 2, 'type': 'evidence', 'desc': f'证据类型: {sum(len(v) for v in evidence.values())}条'},
            {'step': 3, 'type': 'scoring', 'desc': f'评分: {dict(scores)}'},
            {'step': 4, 'type': 'community', 'desc': f'同社区: {comm1.get("name") == comm2.get("name") if comm1 and comm2 else False}'},
            {'step': 5, 'type': 'conclusion', 'desc': f'判定: {best_type} (conf={confidence:.2f})'},
        ]

        return {
            'tool': 'infer_relation',
            'char1': c1,
            'char2': c2,
            'method': method,
            'inferred_type': best_type,
            'confidence': round(confidence, 2),
            'scores': normalized,
            'raw_scores': dict(scores),
            'co_occurrence': co_count,
            'evidence': evidence,
            'reasoning_chain': reasoning_chain,
        }

    def _extract_evidence(self, c1: str, c2: str, limit: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'extract_evidence'}

        ev = {'dialogue': [], 'action': [], 'address': [], 'proximity': []}
        sents = self.store.get_sentences(c1, c2, limit=limit * 3)

        for s in sents:
            sent = s['sentence']

            if '：「' in sent or '」' in sent:
                if len(ev['dialogue']) < limit:
                    ev['dialogue'].append({'text': sent[:200], 'chapter': s.get('chapter', '')})

            for t in ['爷爷', '奶奶', '爹', '娘', '叔', '婶', '姨', '师傅', '师父',
                      '哥', '姐', '妹', '夫妻', '闺蜜', '结婚', '嫁', '娶', '守护']:
                if t in sent and (c1 + t in sent or t + c1 in sent or c2 + t in sent or t + c2 in sent):
                    if len(ev['address']) < limit:
                        ev['address'].append({'term': t, 'text': sent[:200], 'chapter': s.get('chapter', '')})
                    break

            for a in ['一起', '教', '保护', '守护', '背', '送', '帮忙', '救', '打', '住']:
                if a in sent:
                    if len(ev['action']) < limit:
                        ev['action'].append({'action': a, 'text': sent[:200], 'chapter': s.get('chapter', '')})
                    break

            p1, p2 = sent.find(c1), sent.find(c2)
            if p1 != -1 and p2 != -1 and abs(p1 - p2) < 30:
                if len(ev['proximity']) < limit:
                    ev['proximity'].append({'distance': abs(p1 - p2), 'text': sent[:200], 'chapter': s.get('chapter', '')})

        return {
            'tool': 'extract_evidence',
            'char1': c1,
            'char2': c2,
            'evidence': ev,
            'evidence_count': sum(len(v) for v in ev.values()),
        }

    def _plot_prediction(self, current_chapter: int, steps: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'plot_prediction'}

        total = len(self.store.chapters)
        current = min(current_chapter, total) if current_chapter > 0 else total // 2

        predictions = [
            {
                'step': 1,
                'prediction': '主角团队将遭遇更大的危机',
                'basis': '根据剧情节奏，当前阶段后通常会有升级的冲突',
                'probability': 0.8,
            },
            {
                'step': 2,
                'prediction': '某个关键人物的秘密将被揭露',
                'basis': '前文已有多处伏笔暗示人物背景不简单',
                'probability': 0.7,
            },
            {
                'step': 3,
                'prediction': '主角团将迎来战力升级',
                'basis': '遇到更强敌人之前通常会有实力提升的情节',
                'probability': 0.75,
            },
        ]

        return {
            'tool': 'plot_prediction',
            'current_chapter': current,
            'total_chapters': total,
            'predictions': predictions[:steps],
            'note': '基于通用叙事模式的预测，配置 LLM 后可进行更精准的推演',
        }

    def _foreshadow(self, keyword: str, limit: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'foreshadow_analysis'}

        foreshadow_words = ['似乎', '仿佛', '好像', '隐约', '依稀', '似乎', '隐隐', '莫名', '不详', '预感']

        results = []
        if keyword:
            for ch in self.store.chapters:
                content = ch.content
                if keyword not in content:
                    continue
                for sent in re.split(r'[。！？\n]', content):
                    if keyword in sent and any(w in sent for w in foreshadow_words):
                        results.append({
                            'chapter': ch.chapter,
                            'title': ch.title,
                            'sentence': sent.strip()[:200],
                            'foreshadow_words': [w for w in foreshadow_words if w in sent],
                        })
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break
        else:
            for ch in self.store.chapters[:50]:
                content = ch.content
                for sent in re.split(r'[。！？\n]', content):
                    if len(sent) > 15 and any(w in sent for w in foreshadow_words):
                        has_char = any(c in sent for c in self.store.all_chars)
                        if has_char:
                            results.append({
                                'chapter': ch.chapter,
                                'title': ch.title,
                                'sentence': sent.strip()[:200],
                                'foreshadow_words': [w for w in foreshadow_words if w in sent],
                            })
                            if len(results) >= limit:
                                break
                if len(results) >= limit:
                    break

        return {
            'tool': 'foreshadow_analysis',
            'keyword': keyword,
            'results': results,
            'total': len(results),
            'foreshadow_indicators': foreshadow_words,
        }

    def _ending_analysis(self, num_endings: int) -> Dict:
        endings = [
            {
                'type': '圆满结局',
                'probability': 0.4,
                'description': '主角团队战胜最终BOSS，世界恢复和平，主要角色各得其所',
                'supporting_evidence': ['主角光环', '正义终将战胜邪恶的叙事传统'],
            },
            {
                'type': '悲壮结局',
                'probability': 0.3,
                'description': '虽然取得了胜利，但付出了巨大牺牲，重要角色离去',
                'supporting_evidence': ['故事氛围偏凝重', '已有角色牺牲的先例'],
            },
            {
                'type': '开放式结局',
                'probability': 0.2,
                'description': '故事没有明确的结局，留下悬念和想象空间',
                'supporting_evidence': ['悬疑元素较多', '适合续作/番外'],
            },
            {
                'type': '反转结局',
                'probability': 0.1,
                'description': '最终真相出人意料，之前的认知被彻底颠覆',
                'supporting_evidence': ['伏笔众多', '真相层层揭开的叙事结构'],
            },
        ]

        return {
            'tool': 'ending_analysis',
            'endings': endings[:num_endings],
            'total_types': len(endings),
            'note': '基于叙事模式的通用分析，配置 LLM 后可进行更精准的结局推演',
        }

    def _logic_check(self, char_name: str, detail_level: str) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'logic_check'}

        issues = []

        if char_name and char_name in self.store.all_chars:
            positions = self.store.char_index.get(char_name, [])
            ch_appear = defaultdict(list)
            for ci, pos in positions:
                ch_appear[ci].append(pos)

            sorted_chs = sorted(ch_appear.keys())
            gaps = []
            for i in range(1, len(sorted_chs)):
                gap = sorted_chs[i] - sorted_chs[i - 1]
                if gap > 20:
                    gaps.append({
                        'from_chapter': sorted_chs[i - 1] + 1,
                        'to_chapter': sorted_chs[i] + 1,
                        'gap_size': gap,
                    })

            if gaps:
                issues.append({
                    'type': 'appearance_gap',
                    'severity': 'low',
                    'description': f'{char_name} 存在长时间未出场的情况',
                    'details': gaps[:5],
                })

        if not char_name:
            for r in self.store.graph.get('relations', []):
                conf = r.get('confidence', 0.5)
                if conf < 0.4:
                    issues.append({
                        'type': 'low_confidence_relation',
                        'severity': 'medium',
                        'description': f"{r['char1']} ↔ {r['char2']} 关系置信度低 ({conf:.2f})",
                    })
                    if len(issues) >= 10:
                        break

        return {
            'tool': 'logic_check',
            'character': char_name,
            'detail_level': detail_level,
            'issues': issues,
            'issue_count': len(issues),
            'overall_consistency': max(0, 1.0 - len(issues) * 0.05),
        }
