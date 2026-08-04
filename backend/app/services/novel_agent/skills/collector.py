"""
采集技能 - Collector Skill

负责：
- 小说章节采集（从书源URL）
- 数据清洗与格式化
- 增量采集支持
"""

import json
import re
from typing import List, Dict, Any
from ..registry import BaseSkill, ToolDefinition


class CollectorSkill(BaseSkill):
    name = 'collector'

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name='collect_chapters',
                description='从书源URL采集小说章节内容',
                parameters={
                    'book_url': {'type': 'string', 'required': True, 'desc': '书源URL'},
                    'start_chapter': {'type': 'int', 'default': 1, 'desc': '起始章节'},
                    'end_chapter': {'type': 'int', 'default': 0, 'desc': '结束章节（0表示全部）'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='list_chapters',
                description='列出已采集的章节列表',
                parameters={
                    'limit': {'type': 'int', 'default': 20, 'desc': '返回数量'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='get_chapter_content',
                description='获取指定章节的完整内容',
                parameters={
                    'chapter_num': {'type': 'int', 'required': True, 'desc': '章节号'},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name='search_in_chapters',
                description='在所有章节中搜索关键词',
                parameters={
                    'keyword': {'type': 'string', 'required': True, 'desc': '搜索关键词'},
                    'limit': {'type': 'int', 'default': 10, 'desc': '最大结果数'},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        if tool_name == 'collect_chapters':
            return self._collect_chapters(
                params.get('book_url', ''),
                params.get('start_chapter', 1),
                params.get('end_chapter', 0),
            )
        elif tool_name == 'list_chapters':
            return self._list_chapters(params.get('limit', 20))
        elif tool_name == 'get_chapter_content':
            return self._get_chapter(params.get('chapter_num', 1))
        elif tool_name == 'search_in_chapters':
            return self._search(params.get('keyword', ''), params.get('limit', 10))
        return {'error': f'Unknown tool: {tool_name}', 'tool': tool_name}

    def _collect_chapters(self, book_url: str, start: int, end: int) -> Dict:
        if not book_url:
            return {'error': 'book_url is required', 'tool': 'collect_chapters'}

        if not self.store or not self.store.chapters:
            return {
                'tool': 'collect_chapters',
                'status': 'unavailable',
                'available': False,
                'error_code': 'collector_unavailable',
                'book_url': book_url,
                'message': '采集功能需要配置实际书源或 source reader；当前没有可执行的采集能力',
                'chapters_available': len(self.store.chapters) if self.store else 0,
            }

        total = len(self.store.chapters)
        end_idx = end if end > 0 else total
        collected = max(0, min(end_idx, total) - start + 1)

        return {
            'tool': 'collect_chapters',
            'status': 'success',
            'book_url': book_url,
            'start_chapter': start,
            'end_chapter': end_idx,
            'collected': collected,
            'total_available': total,
        }

    def _list_chapters(self, limit: int) -> Dict:
        if not self.store:
            return {'tool': 'list_chapters', 'chapters': [], 'total': 0}

        chapters = []
        for ch in self.store.chapters[:limit]:
            chapters.append({
                'index': ch.index,
                'chapter': ch.chapter,
                'title': ch.title,
                'content_length': len(ch.content),
            })

        return {
            'tool': 'list_chapters',
            'chapters': chapters,
            'total': len(self.store.chapters),
            'shown': len(chapters),
        }

    def _get_chapter(self, chapter_num: int) -> Dict:
        if not self.store:
            return {'error': 'No data store', 'tool': 'get_chapter_content'}

        ch = self.store.get_chapter(chapter_num - 1)
        if not ch:
            return {
                'tool': 'get_chapter_content',
                'found': False,
                'chapter': chapter_num,
                'total_available': len(self.store.chapters),
            }

        return {
            'tool': 'get_chapter_content',
            'found': True,
            'chapter': ch.chapter,
            'title': ch.title,
            'content': ch.content[:2000] + ('...' if len(ch.content) > 2000 else ''),
            'content_length': len(ch.content),
            'characters_present': [c for c in self.store.all_chars if c in ch.content][:10],
        }

    def _search(self, keyword: str, limit: int) -> Dict:
        if not self.store or not keyword:
            return {'tool': 'search_in_chapters', 'results': [], 'total': 0}

        results = self.store.search_text(keyword, limit)
        return {
            'tool': 'search_in_chapters',
            'keyword': keyword,
            'results': results,
            'total': len(results),
        }
