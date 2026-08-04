"""
图谱技能 - Grapher Skill

负责：
- 关系图谱统计
- 图谱生成（HTML可视化）
- 社区发现
- 关系演变分析
"""

import json
from typing import List, Dict, Any
from collections import Counter
from ..registry import BaseSkill, ToolDefinition


class GrapherSkill(BaseSkill):
    name = 'grapher'

    TYPE_COLORS = {
        'family': '#ff6b6b',
        'romance': '#fd79a8',
        'friend': '#74b9ff',
        'companion': '#45b7d1',
        'master': '#4ecdc4',
        'guardian': '#a29bfe',
        'elder': '#f9ca24',
        'antagonist': '#e74c3c',
        'subordinate': '#00b894',
        'ally': '#ffeaa7',
    }

    COMMUNITY_COLORS = [
        '#e94560', '#4ecdc4', '#f9ca24', '#a29bfe',
        '#74b9ff', '#00b894', '#ff7675', '#fdcb6e',
    ]

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='graph_stats',
                description='获取关系图谱统计信息',
                parameters={},
                skill=self.name,
            ),
            ToolDefinition(
                name='generate_graph_html',
                description='生成可视化图谱HTML文件',
                parameters={
                    'output_path': {'type': 'string', 'default': 'data/graph.html', 'desc': '输出文件路径'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='relation_evolution',
                description='分析两人关系的章节演变',
                parameters={
                    'char1': {'type': 'string', 'required': True, 'desc': '人物1'},
                    'char2': {'type': 'string', 'required': True, 'desc': '人物2'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='community_query',
                description='查询社区/阵营信息',
                parameters={
                    'community_name': {'type': 'string', 'desc': '社区名称'},
                    'char_name': {'type': 'string', 'desc': '人物名称'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='get_character_info',
                description='获取人物完整信息',
                parameters={
                    'char_name': {'type': 'string', 'required': True, 'desc': '人物名称'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'graph_stats':
            return self._stats()
        elif tool_name == 'generate_graph_html':
            return self._generate_html(params.get('output_path', 'data/graph.html'))
        elif tool_name == 'relation_evolution':
            return self._evolution(params.get('char1', ''), params.get('char2', ''))
        elif tool_name == 'community_query':
            return self._community_query(
                params.get('community_name', ''),
                params.get('char_name', ''),
            )
        elif tool_name == 'get_character_info':
            return self._char_info(params.get('char_name', ''))
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _stats(self) -> Dict:
        if not self.store:
            return {'tool': 'graph_stats', 'relations': 0, 'characters': 0, 'communities': 0}

        rels = self.store.graph.get('relations', [])
        comms = self.store.graph.get('communities', [])
        n = len(self.store.all_chars)

        type_counts = Counter(r.get('type', 'unknown') for r in rels)
        gt_count = sum(1 for r in rels if r.get('ground_truth'))
        density = round(len(rels) / (n * (n - 1) / 2), 3) if n > 1 else 0

        avg_conf = sum(r.get('confidence', 0.5) for r in rels) / len(rels) if rels else 0

        return {
            'tool': 'graph_stats',
            'characters': n,
            'relations': len(rels),
            'communities': len(comms),
            'relation_types': dict(type_counts),
            'ground_truth_count': gt_count,
            'density': density,
            'avg_confidence': round(avg_conf, 3),
            'chapters': len(self.store.chapters),
            'total_text_chars': len(self.store.full_text),
        }

    def _generate_html(self, output_path: str) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'generate_graph_html'}

        import os
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

        data = self.store.graph
        nodes = []
        for ci_idx, ci in enumerate(data.get('communities', [])):
            for m in ci.get('members', [])[:20]:
                rel_count = sum(
                    1 for r in data.get('relations', [])
                    if r.get('char1') == m or r.get('char2') == m
                )
                size = min(60, max(15, int(rel_count ** 0.5 * 5) if rel_count > 0 else 15))
                nodes.append({
                    'name': m,
                    'symbolSize': size,
                    'category': ci.get('name', f'社区{ci_idx}'),
                    'value': rel_count,
                })

        links = []
        for r in data.get('relations', []):
            links.append({
                'source': r.get('char1', ''),
                'target': r.get('char2', ''),
                'value': r.get('co_count', 0),
                'type': r.get('type', ''),
                'confidence': r.get('confidence', 0.5),
                'ground_truth': r.get('ground_truth', False),
                'description': r.get('description', ''),
            })

        categories = [{'name': ci.get('name', f'社区{i}')} for i, ci in enumerate(data.get('communities', []))]

        safe_json = self._json_for_script
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NovelAgent - 人物关系图谱</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0a0a1a;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}}
.header {{
    padding: 20px;
    text-align: center;
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-bottom: 1px solid #2a2a4a;
}}
.header h1 {{
    font-size: 24px;
    background: linear-gradient(90deg, #e94560, #4ecdc4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.header .subtitle {{
    font-size: 13px;
    color: #888;
    margin-top: 5px;
}}
#chart {{
    width: 100%;
    height: calc(100vh - 80px);
}}
.legend-panel {{
    position: fixed;
    top: 100px;
    right: 20px;
    background: rgba(26, 26, 46, 0.95);
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 15px;
    max-width: 200px;
    font-size: 12px;
    z-index: 100;
}}
.legend-panel h3 {{
    color: #4ecdc4;
    margin-bottom: 10px;
    font-size: 14px;
}}
.legend-item {{
    display: flex;
    align-items: center;
    margin: 5px 0;
}}
.legend-color {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 8px;
}}
</style>
</head>
<body>
<div class="header">
    <h1>NovelAgent · 人物关系图谱</h1>
    <div class="subtitle">基于 DeepSeek-Reasonix 模式的智能分析</div>
</div>
<div id="chart"></div>
<div class="legend-panel">
    <h3>关系类型</h3>
    {''.join(f'<div class="legend-item"><div class="legend-color" style="background:{c}"></div>{t}</div>' for t, c in list(self.TYPE_COLORS.items())[:8])}
</div>
<script>
var chart = echarts.init(document.getElementById('chart'));
var categories = {safe_json(categories)};
var nodes = {safe_json(nodes)};
var links = {safe_json(links)};
var typeColors = {safe_json(self.TYPE_COLORS)};
var commColors = {safe_json(self.COMMUNITY_COLORS)};

function escapeHtml(value) {{
    return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch) {{
        return {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[ch];
    }});
}}

nodes.forEach(function(n) {{
    var ci = 0;
    for (var i = 0; i < categories.length; i++) {{
        if (categories[i].name === n.category) {{ ci = i; break; }}
    }}
    n.itemStyle = {{
        color: commColors[ci % commColors.length],
        borderColor: '#222',
        borderWidth: 2,
        shadowBlur: 10,
        shadowColor: commColors[ci % commColors.length] + '66'
    }};
    n.label = {{ show: true, color: '#fff', fontSize: 11 }};
}});

links.forEach(function(l) {{
    var w = l.ground_truth ? 5 : 2;
    var o = l.ground_truth ? 0.9 : (l.confidence > 0.7 ? 0.7 : 0.4);
    l.lineStyle = {{
        color: typeColors[l.type] || '#666',
        width: w,
        opacity: o,
        curveness: 0.1
    }};
}});

chart.setOption({{
    backgroundColor: '#0a0a1a',
    tooltip: {{
        formatter: function(p) {{
            if (p.dataType === 'node') {{
                return '<b>' + escapeHtml(p.data.name) + '</b><br/>社区: ' + escapeHtml(p.data.category) + '<br/>关系数: ' + escapeHtml(p.data.value);
            }}
            return escapeHtml(p.data.source) + ' ↔ ' + escapeHtml(p.data.target) +
                   '<br/>类型: ' + escapeHtml(p.data.type) +
                   '<br/>置信度: ' + (p.data.confidence || 0.5).toFixed(2) +
                   (p.data.description ? '<br/>描述: ' + escapeHtml(p.data.description) : '');
        }}
    }},
    legend: [{{
        data: categories.map(c => c.name),
        textStyle: {{ color: '#ccc' }},
        top: 10,
        left: 10
    }}],
    series: [{{
        type: 'graph',
        layout: 'force',
        data: nodes,
        links: links,
        categories: categories,
        roam: true,
        draggable: true,
        force: {{
            repulsion: 400,
            gravity: 0.08,
            edgeLength: [80, 220]
        }},
        emphasis: {{ focus: 'adjacency' }},
        lineStyle: {{ curveness: 0.1 }}
    }}]
}});

window.addEventListener('resize', function() {{ chart.resize(); }});
</script>
</body>
</html>'''

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return {
            'tool': 'generate_graph_html',
            'success': True,
            'output_path': output_path,
            'nodes': len(nodes),
            'links': len(links),
            'categories': len(categories),
        }

    @staticmethod
    def _json_for_script(value: Any) -> str:
        """Serialize data without allowing a value to close the script tag."""
        return (
            json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            .replace('<', '\\u003c')
            .replace('>', '\\u003e')
            .replace('&', '\\u0026')
            .replace('\u2028', '\\u2028')
            .replace('\u2029', '\\u2029')
        )

    def _evolution(self, c1: str, c2: str) -> Dict:
        if not self.store:
            return {'tool': 'relation_evolution', 'evolution': [], 'total': 0}

        pair = tuple(sorted([c1, c2]))
        chs = self.store.char_pair_index.get(pair, [])

        evo = []
        if chs:
            max_ch = max(chs)
            step = max(1, (max_ch + 1) // 10)
            for start in range(0, max_ch + 1, step):
                end = start + step
                cnt = sum(1 for ch in chs if start <= ch < end)
                if cnt > 0:
                    evo.append({
                        'range': f'{start + 1}-{end}',
                        'count': cnt,
                        'start_chapter': start + 1,
                        'end_chapter': end,
                    })

        return {
            'tool': 'relation_evolution',
            'char1': c1,
            'char2': c2,
            'co_occurrence_chapters': len(chs),
            'evolution': evo[:20],
        }

    def _community_query(self, community_name: str = '', char_name: str = '') -> Dict:
        if not self.store:
            return {'tool': 'community_query', 'found': False}

        if char_name:
            comm = self.store.get_community(char_name)
            if comm:
                return {
                    'tool': 'community_query',
                    'found': True,
                    'query_type': 'by_char',
                    'char': char_name,
                    'community': comm.get('name', ''),
                    'size': len(comm.get('members', [])),
                    'members': comm.get('members', []),
                }
            return {'tool': 'community_query', 'found': False, 'char': char_name}

        if community_name:
            for ci in self.store.graph.get('communities', []):
                name = ci.get('name', '')
                if community_name == name or community_name in name:
                    return {
                        'tool': 'community_query',
                        'found': True,
                        'query_type': 'by_name',
                        'name': name,
                        'size': len(ci.get('members', [])),
                        'members': ci.get('members', []),
                    }
            return {
                'tool': 'community_query',
                'found': False,
                'available': [ci.get('name', '') for ci in self.store.graph.get('communities', [])],
            }

        all_comms = []
        for ci in self.store.graph.get('communities', []):
            all_comms.append({
                'name': ci.get('name', ''),
                'size': len(ci.get('members', [])),
                'members': ci.get('members', [])[:10],
            })

        return {
            'tool': 'community_query',
            'found': True,
            'query_type': 'all',
            'communities': all_comms,
            'total': len(all_comms),
        }

    def _char_info(self, char_name: str) -> Dict:
        if not self.store:
            return {'tool': 'get_character_info', 'found': False}

        if char_name not in self.store.all_chars:
            return {
                'tool': 'get_character_info',
                'found': False,
                'name': char_name,
            }

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
                    'ground_truth': r.get('ground_truth', False),
                })

        occurrences = self.store.get_character_occurrences(char_name)

        return {
            'tool': 'get_character_info',
            'found': True,
            'name': char_name,
            'community': comm.get('name') if comm else '未知',
            'occurrences': occurrences,
            'relation_count': len(rels),
            'relations': sorted(rels, key=lambda x: -x['confidence']),
        }
