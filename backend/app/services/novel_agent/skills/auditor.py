"""
审计技能 - Auditor Skill

负责：
- 关系质量审计
- 冲突检测
- 别名验证
- 修正建议
"""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
from ..registry import BaseSkill, ToolDefinition


class AuditorSkill(BaseSkill):
    name = 'auditor'

    GROUND_TRUTH = {
        ('谭文彬', '周云云'): ('romance', '未婚夫妻'),
        ('周云云', '陈琳'): ('friend', '闺蜜'),
        ('李追远', '谭文彬'): ('companion', '队友'),
        ('李追远', '阿璃'): ('guardian', '守护灵'),
        ('李追远', '李三江'): ('family', '曾祖孙'),
        ('柳玉梅', '秦叔'): ('family', '同户家人'),
        ('李追远', '李兰'): ('family', '母子'),
        ('李追远', '李维汉'): ('family', '父子'),
        ('魏正道', '书呆子'): ('master', '师徒'),
        ('魏正道', '清安'): ('master', '师徒'),
    }

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='detect_conflicts',
                description='检测关系图谱中的冲突和问题',
                parameters={},
                skill=self.name,
            ),
            ToolDefinition(
                name='trace_reasoning',
                description='追踪关系判定的推理链',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='verify_alias',
                description='验证别名归属关系',
                parameters={
                    'alias': {'type': 'string', 'required': True, 'desc': '待验证的别名'},
                    'main': {'type': 'string', 'required': True, 'desc': '主名称'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='propose_correction',
                description='基于证据提出关系修正建议',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='find_relation',
                description='查找两人之间的关系',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='audit_all',
                description='全量审计所有关系',
                parameters={
                    'min_confidence': {'type': 'float', 'default': 0.5, 'desc': '最低置信度阈值'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'detect_conflicts':
            return self._detect_conflicts()
        elif tool_name == 'trace_reasoning':
            return self._trace_reasoning(params.get('char1', ''), params.get('char2', ''))
        elif tool_name == 'verify_alias':
            return self._verify_alias(params.get('alias', ''), params.get('main', ''))
        elif tool_name == 'propose_correction':
            return self._propose_correction(params.get('char1', ''), params.get('char2', ''))
        elif tool_name == 'find_relation':
            return self._find_relation(params.get('char1', ''), params.get('char2', ''))
        elif tool_name == 'audit_all':
            return self._audit_all(params.get('min_confidence', 0.5))
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _detect_conflicts(self) -> Dict:
        if not self.store:
            return {'tool': 'detect_conflicts', 'conflicts': {}, 'total': 0}

        conflicts = {
            'cross_community': [],
            'low_confidence': [],
            'type_contradiction': [],
            'no_evidence': [],
        }

        char_comm = {}
        for ci in self.store.graph.get('communities', []):
            for m in ci.get('members', []):
                char_comm[m] = ci.get('name', '未知')

        STRONG_TYPES = {'family', 'romance', 'friend', 'master', 'guardian'}

        for r in self.store.graph.get('relations', []):
            c1, c2 = r.get('char1', ''), r.get('char2', '')
            rtype = r.get('type', '')
            conf = r.get('confidence', 0.5)

            if rtype in STRONG_TYPES:
                cm1 = char_comm.get(c1, '?')
                cm2 = char_comm.get(c2, '?')
                if cm1 != cm2 and cm1 != '?' and cm2 != '?':
                    conflicts['cross_community'].append({
                        'pair': f'{c1} ↔ {c2}',
                        'type': rtype,
                        'comm1': cm1,
                        'comm2': cm2,
                    })

            if conf < 0.5:
                conflicts['low_confidence'].append({
                    'pair': f'{c1} ↔ {c2}',
                    'type': rtype,
                    'confidence': conf,
                })

        pair_types = defaultdict(set)
        for r in self.store.graph.get('relations', []):
            pair = tuple(sorted([r.get('char1', ''), r.get('char2', '')]))
            pair_types[pair].add(r.get('type', ''))

        CONTRADICTORY = {('family', 'antagonist'), ('romance', 'antagonist')}
        for pair, types in pair_types.items():
            for t1, t2 in CONTRADICTORY:
                if t1 in types and t2 in types:
                    conflicts['type_contradiction'].append({
                        'pair': f'{pair[0]} ↔ {pair[1]}',
                        'types': list(types),
                    })

        total = sum(len(v) for v in conflicts.values())
        return {
            'tool': 'detect_conflicts',
            'conflicts': conflicts,
            'total': total,
            'summary': {k: len(v) for k, v in conflicts.items()},
        }

    def _trace_reasoning(self, c1: str, c2: str) -> Dict:
        chain = []

        gt = self.GROUND_TRUTH.get((c1, c2)) or self.GROUND_TRUTH.get((c2, c1))
        if gt:
            chain.append({
                'step': 1,
                'type': 'ground_truth',
                'desc': f'Ground Truth: {gt[0]} / {gt[1]}',
                'confidence': 1.0,
            })
            return {
                'tool': 'trace_reasoning',
                'char1': c1,
                'char2': c2,
                'chain': chain,
                'final_type': gt[0],
                'final_description': gt[1],
                'confidence': 1.0,
            }

        ev = self._extract_evidence(c1, c2)
        scores = defaultdict(int)
        evidence_items = []

        for item in ev.get('dialogue', []):
            scores['companion'] += 1
            evidence_items.append({'type': 'dialogue', 'text': item.get('text', '')[:80]})

        for item in ev.get('address', []):
            t = item.get('term', '')
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
            elif t in ['守护']:
                scores['guardian'] += 3
            chain.append({
                'step': len(chain) + 1,
                'type': 'address',
                'desc': f"称谓 '{t}' → 加权",
                'evidence': item.get('text', '')[:80],
            })

        for item in ev.get('action', []):
            a = item.get('action', '')
            if a in ['教', '传授']:
                scores['master'] += 2
            elif a in ['保护', '守护', '救']:
                scores['guardian'] += 2
            elif a in ['一起', '帮忙', '送', '背']:
                scores['companion'] += 1
            elif a in ['住']:
                scores['family'] += 1

        current = None
        cur_conf = 0.5
        if self.store:
            r = self.store.get_relation(c1, c2)
            if r:
                current = r.get('type')
                cur_conf = r.get('confidence', 0.5)
                chain.append({
                    'step': len(chain) + 1,
                    'type': 'current',
                    'desc': f'当前标注: {current} (conf={cur_conf:.2f})',
                })

        if scores:
            best = max(scores, key=lambda k: scores[k])
            total = sum(scores.values())
            conf = scores[best] / total if total > 0 else 0.5
        else:
            best = current or 'companion'
            conf = 0.5

        chain.append({
            'step': len(chain) + 1,
            'type': 'conclusion',
            'desc': f'最终判定: {best} (conf={conf:.2f})',
        })

        return {
            'tool': 'trace_reasoning',
            'char1': c1,
            'char2': c2,
            'chain': chain,
            'final_type': best,
            'confidence': round(conf, 2),
            'evidence_count': len(evidence_items),
            'scores': dict(scores),
        }

    def _extract_evidence(self, c1: str, c2: str) -> Dict:
        ev = {'dialogue': [], 'address': [], 'action': [], 'proximity': []}
        if not self.store:
            return ev

        sents = self.store.get_sentences(c1, c2, limit=30)

        for s in sents:
            sent = s['sentence']

            if '：「' in sent or '」' in sent:
                if len(ev['dialogue']) < 5:
                    ev['dialogue'].append({'text': sent[:200], 'chapter': s.get('chapter', '')})

            for t in ['奶奶', '爷爷', '爹', '娘', '叔', '婶', '姨', '师傅', '师父',
                      '哥', '姐', '妹', '夫妻', '闺蜜', '结婚', '嫁', '娶', '守护']:
                if t in sent and (c1 + t in sent or t + c1 in sent or c2 + t in sent or t + c2 in sent):
                    if len(ev['address']) < 5:
                        ev['address'].append({'term': t, 'text': sent[:200]})
                    break

            for a in ['一起', '教', '保护', '守护', '背', '送', '帮忙', '救', '住']:
                if a in sent:
                    if len(ev['action']) < 5:
                        ev['action'].append({'action': a, 'text': sent[:200]})
                    break

            p1, p2 = sent.find(c1), sent.find(c2)
            if p1 != -1 and p2 != -1 and abs(p1 - p2) < 30:
                if len(ev['proximity']) < 5:
                    ev['proximity'].append({'distance': abs(p1 - p2), 'text': sent[:200]})

        return ev

    def _verify_alias(self, alias: str, main: str) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'verify_alias'}

        alias_count = self.store.full_text.count(alias)
        main_count = self.store.full_text.count(main)

        standalone = 0
        co_occurrence = 0
        for ch in self.store.chapters:
            content = ch.content
            if alias in content:
                ac = content.count(alias)
                if main in content:
                    co_occurrence += ac
                else:
                    standalone += ac

        swap_count = 0
        for ch in self.store.chapters:
            content = ch.content
            if alias in content and main in content:
                for sent in re.split(r'[。！？\n]', content):
                    if alias in sent and main in sent:
                        swap_count += 1

        rate = standalone / alias_count if alias_count > 0 else 1
        is_alias = (rate < 0.5) or (swap_count > 3)

        return {
            'tool': 'verify_alias',
            'alias': alias,
            'main': main,
            'alias_count': alias_count,
            'main_count': main_count,
            'standalone_count': standalone,
            'co_occurrence_count': co_occurrence,
            'swap_count': swap_count,
            'standalone_rate': round(rate, 2),
            'is_alias': is_alias,
            'reason': f'独立率{rate:.0%}，同句交替{swap_count}次 → {"别名" if is_alias else "独立人物"}',
        }

    def _propose_correction(self, c1: str, c2: str) -> Dict:
        trace = self._trace_reasoning(c1, c2)

        current = None
        cur_conf = 0.5
        if self.store:
            r = self.store.get_relation(c1, c2)
            if r:
                current = r.get('type')
                cur_conf = r.get('confidence', 0.5)

        proposed = trace['final_type']
        conf = trace['confidence']

        if current is None:
            suggestion = 'add_new'
            reason = f'新增关系: {proposed}'
        elif proposed != current and conf > 0.6:
            suggestion = 'change_type'
            reason = f'{current} → {proposed} (conf={conf:.2f})'
        elif conf < 0.4:
            suggestion = 'review'
            reason = f'低置信度 ({conf:.2f})，需人工审查'
        else:
            suggestion = 'keep'
            reason = '证据支持当前标注'

        if suggestion in ['change_type', 'add_new'] and self.memory:
            self.memory.add_correction(
                c1, c2, current or 'N/A', proposed,
                str(trace.get('chain', [])), conf
            )

        return {
            'tool': 'propose_correction',
            'char1': c1,
            'char2': c2,
            'current_type': current or 'N/A',
            'current_confidence': cur_conf,
            'proposed_type': proposed,
            'proposed_confidence': conf,
            'suggestion': suggestion,
            'reason': reason,
            'reasoning_chain': trace.get('chain', []),
        }

    def _find_relation(self, c1: str, c2: str) -> Dict:
        if not self.store:
            return {'tool': 'find_relation', 'found': False}

        r = self.store.get_relation(c1, c2)
        if not r:
            return {
                'tool': 'find_relation',
                'found': False,
                'char1': c1,
                'char2': c2,
            }

        return {
            'tool': 'find_relation',
            'found': True,
            'char1': r.get('char1'),
            'char2': r.get('char2'),
            'type': r.get('type'),
            'description': r.get('description', ''),
            'confidence': r.get('confidence', 0.5),
            'co_count': r.get('co_count', 0),
            'ground_truth': r.get('ground_truth', False),
        }

    def _audit_all(self, min_confidence: float) -> Dict:
        if not self.store:
            return {'tool': 'audit_all', 'issues': [], 'total': 0}

        issues = []
        for r in self.store.graph.get('relations', []):
            c1, c2 = r.get('char1', ''), r.get('char2', '')
            conf = r.get('confidence', 0.5)

            if conf < min_confidence:
                issues.append({
                    'type': 'low_confidence',
                    'pair': f'{c1} ↔ {c2}',
                    'relation_type': r.get('type'),
                    'confidence': conf,
                    'severity': 'high' if conf < 0.3 else 'medium',
                })

        return {
            'tool': 'audit_all',
            'issues': issues,
            'total': len(issues),
            'min_confidence': min_confidence,
        }
