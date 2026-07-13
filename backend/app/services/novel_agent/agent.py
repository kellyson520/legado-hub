"""
NovelAgent 核心运行时 - 参考 DeepSeek-Reasonix 的 ReAct 模式

实现：
- ReAct 循环（Think-Act-Observe）
- 意图识别与任务规划
- 工具调用调度
- 结果整合与回答生成
- 多轮迭代优化
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .config import AgentConfig
from .store import NovelDataStore
from .memory import AgentMemory
from .registry import ToolRegistry
from .skills import (
    SourceSkill, CollectorSkill, ExtractorSkill, AuditorSkill, GrapherSkill,
    QASkill, SummarizerSkill, WriterSkill, ReasonerSkill, OCRSkill,
)


@dataclass
class AgentStep:
    """Agent 执行步骤"""
    step: int
    thought: str = ''
    tool: str = ''
    params: Dict = field(default_factory=dict)
    result: Dict = field(default_factory=dict)
    observation: str = ''
    error: str = ''


@dataclass
class AgentResponse:
    """Agent 响应"""
    success: bool
    goal: str
    answer: str
    iterations: int
    steps: List[AgentStep] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict = field(default_factory=dict)


class NovelAgent:
    """小说智能体 - 核心运行时

    参考 DeepSeek-Reasonix 架构：
    - 配置驱动：所有行为通过 AgentConfig 声明
    - 技能插件化：8 大技能动态注册
    - ReAct 循环：Think -> Act -> Observe -> 迭代
    - 项目记忆：SQLite + AGENTS.md
    - MCP 兼容：工具接口符合 MCP 规范
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        store: Optional[NovelDataStore] = None,
        memory: Optional[AgentMemory] = None,
    ):
        self.config = config or AgentConfig()
        self.store = store or NovelDataStore(self.config)
        self.memory = memory or AgentMemory(self.config)

        self.registry = ToolRegistry(self.store, self.memory, self.config)
        self._register_skills()

        self.iteration = 0
        self.history: List[AgentResponse] = []

    def _register_skills(self):
        """根据配置注册技能"""
        skill_classes = [
            SourceSkill,
            CollectorSkill,
            ExtractorSkill,
            AuditorSkill,
            GrapherSkill,
            QASkill,
            SummarizerSkill,
            WriterSkill,
            ReasonerSkill,
            OCRSkill,
        ]

        for skill_cls in skill_classes:
            if self.config.skill_enabled(skill_cls.name):
                skill = skill_cls(self.store, self.memory, self.config)
                self.registry.register_skill(skill)

    def run(self, goal: str, max_iterations: Optional[int] = None) -> AgentResponse:
        """执行 Agent 主循环

        ReAct 模式：
        1. Think: 分析目标，制定计划
        2. Act: 调用工具执行计划
        3. Observe: 观察结果，生成回答
        4. 迭代：如果结果不充分，继续思考-行动
        """
        self.iteration += 1
        max_iter = max_iterations or self.config.get('agent.max_iterations', 20)

        steps: List[AgentStep] = []
        tools_used: List[str] = []
        current_step = 0

        plan = self.think(goal)
        thought = plan.get('thought', '')
        tool_calls = plan.get('steps', [])

        for tc in tool_calls[:max_iter]:
            current_step += 1
            step = AgentStep(
                step=current_step,
                thought=thought if current_step == 1 else '',
                tool=tc.get('tool', ''),
                params=tc.get('params', {}),
            )

            result = self.act(tc.get('tool', ''), tc.get('params', {}))
            step.result = result

            obs = self.observe_single(tc.get('tool', ''), result)
            step.observation = obs

            steps.append(step)
            if tc.get('tool') not in tools_used:
                tools_used.append(tc.get('tool', ''))

        answer = self.synthesize(goal, steps)

        response = AgentResponse(
            success=True,
            goal=goal,
            answer=answer,
            iterations=current_step,
            steps=steps,
            tools_used=tools_used,
            confidence=self._calculate_confidence(steps),
            metadata={
                'agent_name': self.config.get('agent.name', 'NovelAgent'),
                'agent_version': self.config.get('agent.version', '2.0.0'),
            },
        )

        self.memory.add_qa(goal, answer, '', tools_used)
        self.memory.add_to_conversation('user', goal)
        self.memory.add_to_conversation('assistant', answer, {'tools': tools_used})
        self.history.append(response)

        return response

    def think(self, goal: str) -> Dict[str, Any]:
        """思考阶段：分析目标，制定工具调用计划

        基于规则的规划器（可替换为 LLM 规划）
        参考 Reasonix 的 planner-executor 双模型架构
        """
        plan = {
            'goal': goal,
            'thought': '',
            'steps': [],
        }

        chars_in_goal = [c for c in self.store.all_chars if c in goal]
        goal_lower = goal.lower()

        # 书源相关（优先匹配）
        if any(k in goal for k in ['书源', 'source', '找书源', '搜书源', '书源搜索']):
            if any(k in goal for k in ['找', '搜', '搜索', '查找']):
                import re
                m = re.search(r'(?:找|搜|搜索|查找)(.+?)(?:的|书源|$)', goal)
                keyword = m.group(1).strip() if m else "斗破苍穹"
                plan['thought'] = f'搜索「{keyword}」相关书源'
                plan['steps'] = [
                    {'tool': 'source_search', 'params': {'keyword': keyword, 'limit': 10}},
                    {'tool': 'source_list', 'params': {'keyword': keyword}},
                ]
            else:
                plan['thought'] = '查看书源列表'
                plan['steps'] = [
                    {'tool': 'source_list', 'params': {}},
                    {'tool': 'source_groups', 'params': {}},
                ]

        elif any(k in goal for k in ['爬书源', '自动书源', '分析网站', '爬取书源', '生成书源']):
            import re
            m = re.search(r'https?://[^\s，。]+', goal)
            site_url = m.group(0) if m else ""
            if site_url:
                plan['thought'] = f'自动分析站点 {site_url} 生成书源'
                plan['steps'] = [
                    {'tool': 'source_crawl_site', 'params': {'site_url': site_url}},
                    {'tool': 'source_template', 'params': {}},
                ]
            else:
                plan['thought'] = '生成书源模板'
                plan['steps'] = [
                    {'tool': 'source_template', 'params': {}},
                    {'tool': 'source_list', 'params': {}},
                ]

        elif any(k in goal for k in ['写书源', '编写书源', '创建书源', '新增书源', '添加书源']):
            plan['thought'] = '创建新书源'
            plan['steps'] = [
                {'tool': 'source_template', 'params': {}},
                {'tool': 'source_list', 'params': {}},
            ]

        elif any(k in goal for k in ['验证书源', '书源验证', '测试书源']):
            plan['thought'] = '验证书源有效性'
            plan['steps'] = [
                {'tool': 'source_list', 'params': {}},
            ]

        elif any(k in goal for k in ['导入书源', '导出书源', '书源导入', '书源导出']):
            plan['thought'] = '书源导入/导出管理'
            plan['steps'] = [
                {'tool': 'source_list', 'params': {}},
                {'tool': 'source_groups', 'params': {}},
            ]

        elif any(k in goal for k in ['关系', '什么关系', '两人', '之间', '是什么关系']):
            if len(chars_in_goal) >= 2:
                c1, c2 = chars_in_goal[0], chars_in_goal[1]
                plan['thought'] = f'分析 {c1} 和 {c2} 的关系，综合多种证据'
                plan['steps'] = [
                    {'tool': 'find_relation', 'params': {'char1': c1, 'char2': c2}},
                    {'tool': 'extract_evidence', 'params': {'char1': c1, 'char2': c2, 'limit': 3}},
                    {'tool': 'infer_relation', 'params': {'char1': c1, 'char2': c2, 'method': 'hybrid'}},
                    {'tool': 'trace_reasoning', 'params': {'char1': c1, 'char2': c2}},
                ]

        elif any(k in goal for k in ['统计', '多少', '数量', '数据']):
            plan['thought'] = '获取统计数据'
            plan['steps'] = [
                {'tool': 'graph_stats', 'params': {}},
                {'tool': 'extract_characters', 'params': {'min_occurrences': 2}},
            ]

        elif any(k in goal for k in ['审计', '检查', '问题', '冲突', '错误', '质量']):
            plan['thought'] = '执行图谱质量审计，检测冲突和问题'
            plan['steps'] = [
                {'tool': 'detect_conflicts', 'params': {}},
                {'tool': 'graph_stats', 'params': {}},
                {'tool': 'audit_all', 'params': {'min_confidence': 0.5}},
            ]

        elif any(k in goal for k in ['人物', '角色', '介绍', '是谁', '什么样的人', '简介']):
            if chars_in_goal:
                char = chars_in_goal[0]
                plan['thought'] = f'生成 {char} 的人物档案'
                plan['steps'] = [
                    {'tool': 'get_character_info', 'params': {'char_name': char}},
                    {'tool': 'character_profile', 'params': {'char_name': char}},
                    {'tool': 'character_timeline', 'params': {'char_name': char, 'limit': 5}},
                ]

        elif any(k in goal for k in ['图谱', '生成图', '画图', '可视化', '关系图']):
            plan['thought'] = '生成关系图谱可视化'
            plan['steps'] = [
                {'tool': 'graph_stats', 'params': {}},
                {'tool': 'generate_graph_html', 'params': {'output_path': 'data/graph.html'}},
            ]

        elif re.search(r'第\d+章', goal):
            m = re.search(r'第(\d+)章', goal)
            if m:
                ch_num = int(m.group(1))
                plan['thought'] = f'分析第 {ch_num} 章内容'
                plan['steps'] = [
                    {'tool': 'chapter_summary', 'params': {'chapter_num': ch_num}},
                ]

        elif any(k in goal for k in ['情节', '找', '搜索', '哪一章', '哪里']):
            m = re.search(r'[「"]([^」"]+)[」"]', goal)
            kw = m.group(1) if m else (chars_in_goal[0] if chars_in_goal else goal[:10])
            plan['thought'] = f'搜索情节关键词: {kw}'
            plan['steps'] = [
                {'tool': 'plot_search', 'params': {'keyword': kw, 'limit': 5}},
            ]

        elif any(k in goal for k in ['社区', '阵营', '队伍', '派系', '团体']):
            plan['thought'] = '查询社区/阵营信息'
            plan['steps'] = [
                {'tool': 'community_query', 'params': {}},
                {'tool': 'graph_stats', 'params': {}},
            ]

        elif any(k in goal for k in ['别名', '是不是', '同一个人', '绰号']):
            if len(chars_in_goal) >= 2:
                plan['thought'] = f'验证 {chars_in_goal[0]} 和 {chars_in_goal[1]} 是否为同一人'
                plan['steps'] = [
                    {'tool': 'verify_alias', 'params': {'alias': chars_in_goal[0], 'main': chars_in_goal[1]}},
                ]

        elif any(k in goal for k in ['修正', '建议', '改进', '优化']):
            if len(chars_in_goal) >= 2:
                c1, c2 = chars_in_goal[0], chars_in_goal[1]
                plan['thought'] = f'分析 {c1} 和 {c2} 的关系，提出修正建议'
                plan['steps'] = [
                    {'tool': 'propose_correction', 'params': {'char1': c1, 'char2': c2}},
                ]

        elif any(k in goal for k in ['演变', '发展', '变化', '走势']):
            if len(chars_in_goal) >= 2:
                c1, c2 = chars_in_goal[0], chars_in_goal[1]
                plan['thought'] = f'分析 {c1} 和 {c2} 关系的演变'
                plan['steps'] = [
                    {'tool': 'relation_evolution', 'params': {'char1': c1, 'char2': c2}},
                ]

        elif any(k in goal for k in ['续写', '写', '创作', '生成']):
            plan['thought'] = '生成写作内容'
            plan['steps'] = [
                {'tool': 'generate_continuation', 'params': {'prompt': goal, 'length': 500}},
            ]

        elif any(k in goal for k in ['概要', '总结', '简介', '概述', '讲了什么']):
            plan['thought'] = '生成全书概要'
            plan['steps'] = [
                {'tool': 'book_overview', 'params': {'max_length': 1000}},
                {'tool': 'graph_stats', 'params': {}},
            ]

        elif any(k in goal for k in ['主题', '主旨', '核心']):
            plan['thought'] = '分析小说主题'
            plan['steps'] = [
                {'tool': 'theme_analysis', 'params': {'top_n': 10}},
            ]

        elif any(k in goal for k in ['伏笔', '暗示', '铺垫', '预测', '结局']):
            plan['thought'] = '分析伏笔和剧情走向'
            plan['steps'] = [
                {'tool': 'foreshadow_analysis', 'params': {'limit': 10}},
                {'tool': 'ending_analysis', 'params': {'ending_types': 3}},
            ]

        elif any(k in goal for k in ['对比', '比较', '区别']):
            if len(chars_in_goal) >= 2:
                c1, c2 = chars_in_goal[0], chars_in_goal[1]
                plan['thought'] = f'对比 {c1} 和 {c2}'
                plan['steps'] = [
                    {'tool': 'compare_characters', 'params': {'char1': c1, 'char2': c2}},
                ]

        else:
            plan['thought'] = '通用问答，尝试多工具查询'
            plan['steps'] = [
                {'tool': 'graph_stats', 'params': {}},
                {'tool': 'answer_question', 'params': {'question': goal, 'context_chars': 200}},
            ]

        max_tools = self.config.get('agent.max_tool_calls_per_step', 5)
        plan['steps'] = plan['steps'][:max_tools]

        return plan

    def act(self, tool_name: str, params: Dict) -> Dict:
        """行动阶段：调用工具执行"""
        return self.registry.call(tool_name, **params)

    def observe_single(self, tool_name: str, result: Dict) -> str:
        """观察阶段：解读单个工具结果"""
        if 'error' in result:
            return f"[{tool_name}] 错误: {result['error']}"

        if tool_name == 'find_relation' and result.get('found'):
            return f"关系: {result.get('char1')} ↔ {result.get('char2')} ({result.get('type')}, conf={result.get('confidence', 0):.2f})"
        elif tool_name == 'find_relation':
            return '未找到关系记录'

        if tool_name == 'get_character_info':
            return f"人物: {result.get('name')}，社区: {result.get('community')}，关系: {result.get('relation_count')}条"

        if tool_name == 'graph_stats':
            return f"图谱: {result.get('characters', 0)}人，{result.get('relations', 0)}关系，{result.get('communities', 0)}社区"

        if tool_name == 'detect_conflicts':
            total = result.get('total', 0)
            return f"检测到 {total} 个冲突问题" if total > 0 else "未检测到明显冲突"

        if tool_name == 'chapter_summary':
            return f"第{result.get('chapter')}章: {result.get('title', '')}，出场{result.get('character_count', 0)}人"

        if tool_name == 'plot_search':
            return f"找到 {result.get('total', 0)} 处相关情节"

        if tool_name == 'community_query':
            if result.get('found') and 'communities' in result:
                return f"共 {result.get('total', 0)} 个社区"
            elif result.get('found'):
                return f"社区: {result.get('name', result.get('community', ''))}"
            return '未找到社区信息'

        if tool_name == 'generate_graph_html':
            return f"图谱已生成: {result.get('output_path')} ({result.get('nodes', 0)}节点)"

        if tool_name == 'recall_context':
            return f"召回 {result.get('sampled', 0)} 个上下文片段，共 {result.get('total_occurrences', 0)} 次出现"

        if tool_name == 'extract_evidence':
            return f"提取到 {result.get('evidence_count', 0)} 条证据"

        if tool_name == 'infer_relation':
            return f"推理关系: {result.get('inferred_type')} (conf={result.get('confidence', 0):.2f})"

        if tool_name == 'trace_reasoning':
            return f"推理链: {len(result.get('chain', []))} 步 → {result.get('final_type', '')}"

        if tool_name == 'verify_alias':
            return f"别名验证: {'是' if result.get('is_alias') else '非'} 别名"

        if tool_name == 'propose_correction':
            return f"修正建议: {result.get('suggestion', '')} - {result.get('reason', '')}"

        if tool_name == 'character_profile':
            return f"人物档案: {result.get('name')}，{result.get('occurrences', 0)}次出场"

        if tool_name == 'character_timeline':
            return f"时间线: 共{result.get('total_chapters', 0)}章出场"

        if tool_name == 'book_overview':
            return f"全书概要: {result.get('stats', {}).get('chapters', 0)}章"

        if tool_name == 'answer_question':
            return f"回答: {result.get('answer', '')[:100]}..." if result.get('answer') else '未找到答案'

        if tool_name == 'theme_analysis':
            return f"主题分析: 前{result.get('top_n', 0)}个主题"

        if tool_name == 'compare_characters':
            return f"对比: {result.get('char1')} vs {result.get('char2')}，共现{result.get('co_occurrence_chapters', 0)}章"

        if tool_name == 'relation_evolution':
            return f"关系演变: 共现{result.get('co_occurrence_chapters', 0)}章"

        if tool_name == 'search_pattern':
            return f"模式匹配: {result.get('total', 0)} 条结果"

        if tool_name == 'extract_characters':
            return f"抽取人物: {result.get('total', 0)} 个"

        if tool_name == 'generate_continuation':
            return f"续写生成: {len(result.get('content', ''))} 字"

        return f"[{tool_name}] 执行完成"

    def synthesize(self, goal: str, steps: List[AgentStep]) -> str:
        """综合阶段：整合所有步骤结果，生成最终回答"""
        parts = []

        for step in steps:
            tool = step.tool
            result = step.result

            if 'error' in result:
                parts.append(f"⚠️ [{tool}] {result['error']}")
                continue

            if tool == 'find_relation' and result.get('found'):
                parts.append(
                    f"📌 {result.get('char1')} ↔ {result.get('char2')}\n"
                    f"   类型: {result.get('type')}\n"
                    f"   描述: {result.get('description', '无')}\n"
                    f"   置信度: {result.get('confidence', 0):.2f}"
                )
            elif tool == 'find_relation':
                parts.append('📌 未找到已标注的关系记录')

            elif tool == 'get_character_info':
                rels = result.get('relations', [])
                rel_str = ', '.join(f"{r['character']}({r['type']})" for r in rels[:5])
                parts.append(
                    f"👤 {result.get('name')}\n"
                    f"   社区: {result.get('community')}\n"
                    f"   出场: {result.get('occurrences')}次\n"
                    f"   关系: {result.get('relation_count')}条\n"
                    f"   主要关系: {rel_str}"
                )

            elif tool == 'character_profile':
                parts.append(result.get('profile', ''))

            elif tool == 'graph_stats':
                types = ', '.join(f"{k}({v})" for k, v in list(result.get('relation_types', {}).items())[:6])
                parts.append(
                    f"📊 图谱统计\n"
                    f"   人物: {result.get('characters', 0)}人\n"
                    f"   关系: {result.get('relations', 0)}条\n"
                    f"   社区: {result.get('communities', 0)}个\n"
                    f"   密度: {result.get('density', 0)}\n"
                    f"   平均置信度: {result.get('avg_confidence', 0)}\n"
                    f"   类型: {types}"
                )

            elif tool == 'detect_conflicts':
                total = result.get('total', 0)
                parts.append(f"⚠️ 冲突检测: {total} 个问题")
                summary = result.get('summary', {})
                for ct, cnt in summary.items():
                    if cnt > 0:
                        parts.append(f"   - {ct}: {cnt}条")
                conflicts = result.get('conflicts', {})
                for ct, items in conflicts.items():
                    if items:
                        for it in items[:2]:
                            if isinstance(it, dict):
                                parts.append(f"     • {it.get('pair', '')}")
                            else:
                                parts.append(f"     • {it}")

            elif tool == 'chapter_summary':
                chars = ', '.join(result.get('characters_present', [])[:8])
                keys = '\n'.join(f"     • {s}" for s in result.get('key_sentences', [])[:3])
                parts.append(
                    f"📖 第{result.get('chapter')}章: {result.get('title', '')}\n"
                    f"   字数: {result.get('content_length', 0)}\n"
                    f"   出场({result.get('character_count', 0)}): {chars}\n"
                    f"   关键句:\n{keys}"
                )

            elif tool == 'plot_search':
                parts.append(f"🔍 「{result.get('keyword', '')}」找到 {result.get('total', 0)} 处")
                for i, r2 in enumerate(result.get('results', [])[:3], 1):
                    parts.append(f"   {i}. [{r2.get('chapter', '')}] {r2.get('context', '')[:100]}...")

            elif tool == 'community_query':
                if 'communities' in result:
                    parts.append(f"🏘️ 共 {result.get('total', 0)} 个社区")
                    for comm in result.get('communities', []):
                        members = ', '.join(comm.get('members', [])[:8])
                        parts.append(f"   • {comm.get('name', '')} ({comm.get('size', 0)}人): {members}")
                elif result.get('found'):
                    name = result.get('name', result.get('community', ''))
                    size = result.get('size', 0)
                    members = ', '.join(result.get('members', [])[:10])
                    parts.append(f"🏘️ {name} ({size}人)\n   成员: {members}")

            elif tool == 'generate_graph_html':
                parts.append(
                    f"🖼️ 图谱已生成\n"
                    f"   文件: {result.get('output_path')}\n"
                    f"   节点: {result.get('nodes', 0)}\n"
                    f"   连线: {result.get('links', 0)}"
                )

            elif tool == 'recall_context':
                parts.append(
                    f"💭 上下文召回\n"
                    f"   人物: {result.get('character')}\n"
                    f"   总出现: {result.get('total_occurrences')}次\n"
                    f"   采样: {result.get('sampled')} 个片段"
                )
                for ctx in result.get('contexts', [])[:3]:
                    parts.append(f"   [{ctx.get('chapter')}] {ctx.get('context', '')[:80]}...")

            elif tool == 'extract_evidence':
                parts.append(
                    f"📝 {result.get('char1')} ↔ {result.get('char2')} 证据\n"
                    f"   共 {result.get('evidence_count', 0)} 条证据"
                )
                ev = result.get('evidence', {})
                for etype, items in ev.items():
                    if items:
                        parts.append(f"   [{etype}] {len(items)}条")
                        for it in items[:2]:
                            text = it if isinstance(it, str) else it.get('text', '')
                            parts.append(f"     • {text[:80]}...")

            elif tool == 'infer_relation':
                parts.append(
                    f"🧠 关系推理\n"
                    f"   {result.get('char1')} ↔ {result.get('char2')}\n"
                    f"   推理结果: {result.get('inferred_type')} (conf={result.get('confidence', 0):.2f})\n"
                    f"   评分分布: {result.get('scores', {})}"
                )

            elif tool == 'trace_reasoning':
                parts.append("🔗 推理链:")
                for step_item in result.get('chain', []):
                    parts.append(f"   Step{step_item.get('step')} [{step_item.get('type')}]: {step_item.get('desc')}")
                parts.append(f"   → {result.get('final_type', '')} (conf={result.get('final_confidence', result.get('confidence', 0)):.2f})")

            elif tool == 'verify_alias':
                status = '✓ 是别名' if result.get('is_alias') else '✗ 非别名（独立人物）'
                parts.append(
                    f"🔤 别名验证\n"
                    f"   {result.get('alias')} → {result.get('main')}\n"
                    f"   {status}\n"
                    f"   理由: {result.get('reason')}"
                )

            elif tool == 'propose_correction':
                parts.append(
                    f"💡 修正建议\n"
                    f"   {result.get('char1')} ↔ {result.get('char2')}\n"
                    f"   当前: {result.get('current_type')} → 建议: {result.get('proposed_type')}\n"
                    f"   动作: {result.get('suggestion')}\n"
                    f"   理由: {result.get('reason')}"
                )

            elif tool == 'character_timeline':
                parts.append(f"⏱️ {result.get('character')} 出场时间线 ({result.get('total_chapters')}章)")
                for t in result.get('timeline', [])[:5]:
                    parts.append(f"   第{t.get('chapter')}章 ({t.get('title', '')}): {t.get('first_context', '')[:60]}...")

            elif tool == 'book_overview':
                parts.append(result.get('overview', ''))

            elif tool == 'theme_analysis':
                parts.append("🎯 主题分析")
                for t in result.get('themes', [])[:5]:
                    parts.append(f"   {t.get('theme')}: {t.get('percentage')}%")

            elif tool == 'compare_characters':
                parts.append(
                    f"⚖️ {result.get('char1')} vs {result.get('char2')}\n"
                    f"   共现: {result.get('co_occurrence_chapters')}章\n"
                    f"   关系: {result.get('relation_type', 'unknown')} - {result.get('relation_description', '')}\n"
                    f"   同社区: {'是' if result.get('same_community') else '否'}\n"
                    f"   社区: {result.get('community_1')} / {result.get('community_2')}"
                )

            elif tool == 'relation_evolution':
                parts.append(f"📈 {result.get('char1')} ↔ {result.get('char2')} 关系演变")
                for e in result.get('evolution', [])[:5]:
                    parts.append(f"   {e.get('range')}章: {e.get('count')}次共现")

            elif tool == 'answer_question':
                answer = result.get('answer', '')
                conf = result.get('confidence', 0)
                parts.append(
                    f"💬 问答\n"
                    f"   问题: {goal}\n"
                    f"   置信度: {conf:.0%}\n"
                    f"   回答: {answer}"
                )

            elif tool == 'search_pattern':
                parts.append(f"🔍 模式「{result.get('pattern_type')}」匹配 {result.get('total', 0)} 条")
                for m in result.get('results', [])[:3]:
                    parts.append(f"   [{m.get('chapter', '')}] {m.get('match', '')}")

            elif tool == 'extract_characters':
                parts.append(f"👥 抽取人物 {result.get('total', 0)} 个")
                for c in result.get('characters', [])[:5]:
                    parts.append(f"   • {c.get('name')} ({c.get('occurrences')}次, {c.get('community')})")

            elif tool == 'audit_all':
                parts.append(f"🔍 全量审计: 发现 {result.get('total', 0)} 个问题")

            elif tool == 'generate_continuation':
                parts.append(
                    f"✍️ 续写生成\n"
                    f"   {result.get('content', '')[:300]}..."
                )

            elif tool == 'foreshadow_analysis':
                parts.append(f"🔮 伏笔分析: 发现 {result.get('total', 0)} 处伏笔")
                for f in result.get('results', [])[:3]:
                    parts.append(f"   [{f.get('chapter', '')}] {f.get('sentence', '')[:80]}...")

            elif tool == 'ending_analysis':
                parts.append("📚 结局走向分析")
                for e in result.get('endings', []):
                    parts.append(f"   {e.get('type')} ({e.get('probability'):.0%}): {e.get('description', '')[:50]}")

            elif tool == 'logic_check':
                parts.append(
                    f"✅ 逻辑检查\n"
                    f"   整体一致性: {result.get('overall_consistency', 0):.0%}\n"
                    f"   问题数: {result.get('issue_count', 0)}"
                )

            else:
                parts.append(f"[{tool}] {str(result)[:200]}")

        return '\n\n'.join(parts)

    def _calculate_confidence(self, steps: List[AgentStep]) -> float:
        """计算回答置信度"""
        if not steps:
            return 0.0
        success_steps = sum(1 for s in steps if 'error' not in s.result)
        base_conf = success_steps / len(steps) if steps else 0
        return round(min(1.0, base_conf + 0.1), 2)

    def list_available_tools(self) -> List[Dict]:
        """列出所有可用工具"""
        return self.registry.list_tools()

    def list_available_skills(self) -> List[str]:
        """列出所有已注册技能"""
        return self.registry.skills

    def get_stats(self) -> Dict:
        """获取 Agent 统计信息"""
        return {
            'agent': {
                'name': self.config.get('agent.name'),
                'version': self.config.get('agent.version'),
                'iteration': self.iteration,
            },
            'skills': self.list_available_skills(),
            'tools': len(self.list_available_tools()),
            'memory': self.memory.stats() if self.memory else {},
            'data': self.store.stats() if self.store else {},
        }

    def chat(self, message: str) -> str:
        """简单聊天接口"""
        response = self.run(message)
        return response.answer
