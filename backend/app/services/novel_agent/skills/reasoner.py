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
from ._provider import complete_text


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
            return {
                'tool': 'plot_prediction',
                'predictions': [],
                'available': False,
                'status': 'unavailable',
                'error_code': 'novel_data_unavailable',
            }

        total = len(self.store.chapters)
        current = min(current_chapter, total) if current_chapter > 0 else total // 2

        provider_text = complete_text(
            self.provider,
            f"请根据小说当前第{current}章（共{total}章）的上下文预测后续{steps}步发展，给出证据和概率。",
            system="你是小说推理助手。不要编造未提供的事实，只输出有证据的预测。",
        )
        if provider_text:
            return {
                'tool': 'plot_prediction',
                'current_chapter': current,
                'total_chapters': total,
                'predictions': [
                    {
                        'step': 1,
                        'prediction': provider_text,
                        'basis': 'configured_provider',
                        'probability': None,
                    }
                ],
                'generated': provider_text,
                'available': True,
                'status': 'completed',
                'mode': 'provider',
            }

        predictions = []
        for step, chapter in enumerate(self.store.chapters[current:current + max(0, steps)], 1):
            evidence = (chapter.content or "").strip().replace("\n", " ")[:240]
            predictions.append(
                {
                    'step': step,
                    'prediction': f"第{chapter.chapter}章将围绕《{chapter.title or '未命名章节'}》展开",
                    'basis': f"后续章节原文证据：{evidence}" if evidence else '后续章节存在但没有可用正文',
                    'probability': 0.5 if evidence else 0.0,
                }
            )

        return {
            'tool': 'plot_prediction',
            'current_chapter': current,
            'total_chapters': total,
            'predictions': predictions[:steps],
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；这里只返回后续章节的原文证据，不代表模型预测',
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
        if not self.store:
            return {
                'tool': 'ending_analysis',
                'endings': [],
                'total_types': 0,
                'available': False,
                'status': 'unavailable',
                'error_code': 'novel_data_unavailable',
            }

        recent_text = "\n".join(ch.content or "" for ch in self.store.chapters[-5:])
        provider_text = complete_text(
            self.provider,
            f"请根据小说最后几章分析最多{num_endings}种可能结局，并逐条引用证据。\n{recent_text[:6000]}",
            system="你是小说推理助手。结论必须区分原文证据和推测。",
        )
        if provider_text:
            return {
                'tool': 'ending_analysis',
                'endings': [{'type': 'provider_analysis', 'description': provider_text, 'supporting_evidence': []}],
                'total_types': 1,
                'generated': provider_text,
                'available': True,
                'status': 'completed',
                'mode': 'provider',
            }

        signal_groups = [
            ('圆满结局倾向', ('胜利', '和平', '团聚', '归来', '重建')),
            ('悲剧结局倾向', ('死亡', '牺牲', '诀别', '毁灭', '永远离开')),
            ('开放结局倾向', ('谜团', '未知', '等待', '未完', '新的旅程')),
            ('反转结局倾向', ('真相', '阴谋', '原来', '竟然', '身份')),
        ]
        endings = []
        for ending_type, terms in signal_groups:
            evidence = [
                sentence.strip()[:180]
                for sentence in re.split(r'[。！？\n]', recent_text)
                if sentence.strip() and any(term in sentence for term in terms)
            ][:3]
            if evidence:
                endings.append(
                    {
                        'type': ending_type,
                        'probability': round(min(0.9, 0.3 + len(evidence) * 0.1), 2),
                        'description': '根据末章文本信号形成的待验证倾向',
                        'supporting_evidence': evidence,
                    }
                )
        endings = endings[:max(0, int(num_endings))]
        if not endings:
            endings = [{
                'type': 'insufficient_evidence',
                'probability': 0.0,
                'description': '末章没有足够的结局信号，无法进行可靠预测',
                'supporting_evidence': [],
            }]

        return {
            'tool': 'ending_analysis',
            'endings': endings[:num_endings],
            'total_types': len(endings),
            'available': False,
            'status': 'unavailable',
            'error_code': 'provider_unavailable',
            'note': '未配置可用 Provider；结局候选仅由末章文本信号生成，不代表模型结论',
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
