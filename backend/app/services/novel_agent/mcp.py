"""
MCP (Model Context Protocol) 工具接口

参考 DeepSeek-Reasonix 的 MCP 兼容设计
将 NovelAgent 的工具通过 MCP 协议暴露给外部 LLM 使用

MCP 协议参考：
- tools/list: 列出可用工具列表
- tools/call: 调用工具
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .agent import NovelAgent


class MCPInterface:
    """MCP 协议接口

    提供标准 MCP 工具调用接口，使 NovelAgent 的工具可以被任何 MCP 客户端调用。
    参考 Reasonix 的插件化 MCP 设计。
    """

    def __init__(self, agent: NovelAgent):
        self.agent = agent

    def list_tools(self) -> Dict[str, Any]:
        """MCP tools/list 方法：列出可用工具"""
        tools = self.agent.list_available_tools()
        mcp_tools = []
        for t in tools:
            mcp_tools.append({
                'name': t['name'],
                'description': t['description'],
                'inputSchema': {
                    'type': 'object',
                    'properties': t.get('parameters', {}),
                },
            })
        return {
            'tools': mcp_tools,
        }

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """MCP tools/call 方法：调用工具"""
        result = self.agent.registry.call(tool_name, **arguments)

        if 'error' in result:
            return {
                'content': [
                    {
                        'type': 'text',
                        'text': json.dumps(result, ensure_ascii=False, indent=2),
                    }
                ],
                'isError': True,
            }

        return {
            'content': [
                {
                    'type': 'text',
                    'text': json.dumps(result, ensure_ascii=False, indent=2),
                }
            ],
        }

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理 MCP 请求"""
        method = request.get('method', '')
        params = request.get('params', {})

        if method == 'tools/list':
            return self.list_tools()
        elif method == 'tools/call':
            tool_name = params.get('name', '')
            arguments = params.get('arguments', {})
            return self.call_tool(tool_name, arguments)
        elif method == 'initialize':
            return {
                'protocolVersion': '2024-11-05',
                'capabilities': {
                    'tools': {},
                },
                'serverInfo': {
                    'name': 'novel-agent-mcp',
                    'version': '2.0.0',
                },
            }
        else:
            return {
                'error': {
                    'code': -32601,
                    'message': f'Method not found: {method}',
                }
            }

    def get_tool_definitions_json(self) -> str:
        """获取 JSON 格式的工具定义（供 LLM function calling 使用）"""
        tools = self.agent.list_available_tools()
        definitions = []
        for t in tools:
            definitions.append({
                'type': 'function',
                'function': {
                    'name': t['name'],
                    'description': t['description'],
                    'parameters': {
                        'type': 'object',
                        'properties': t.get('parameters', {}),
                    },
                },
            })
        return json.dumps(definitions, ensure_ascii=False, indent=2)
