"""
工具注册表 - 参考 DeepSeek-Reasonix 的插件化工具设计

技能（Skill）自注册工具，支持动态启用/禁用。
每个技能提供一组工具，工具可以被 Agent 通过 ReAct 循环调用。
"""

import abc
import asyncio
import fnmatch
import time
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    skill: str = ''


class BaseSkill(abc.ABC):
    """技能基类

    每个技能封装一组相关工具，参考 Reasonix 的插件化设计。
    技能自注册：通过 get_tools() 声明提供的工具。
    """

    name: str = 'base'

    def __init__(self, store=None, memory=None, config=None, provider=None):
        self.store = store
        self.memory = memory
        self.config = config
        configured_provider = None
        getter = getattr(config, "get", None)
        if callable(getter):
            configured_provider = getter("llm_provider", None) or getter("provider", None)
        elif isinstance(config, dict):
            configured_provider = config.get("llm_provider") or config.get("provider")
        self.provider = provider or configured_provider

    @abc.abstractmethod
    def get_tools(self) -> List[ToolDefinition]:
        """返回该技能提供的工具列表"""
        pass

    @abc.abstractmethod
    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        """执行指定工具"""
        pass


class ToolRegistry:
    """工具注册表

    管理所有技能提供的工具，支持：
    - 技能动态注册/注销
    - 工具按配置启用/禁用
    - 工具调用调度
    - 工具元数据查询（供 LLM 选择工具使用）
    """

    def __init__(self, store=None, memory=None, config=None):
        self.store = store
        self.memory = memory
        self.config = config
        self._tools: Dict[str, Dict] = {}
        self._skills: Dict[str, BaseSkill] = {}

    def register_skill(self, skill: BaseSkill):
        """注册一个技能及其所有工具"""
        self._skills[skill.name] = skill
        for tool_def in skill.get_tools():
            tool_name = tool_def.name
            if self._is_tool_enabled(tool_name):
                self._tools[tool_name] = {
                    'def': tool_def,
                    'skill': skill,
                }

    def register_external_tool(self, tool_def: ToolDefinition, handler: Callable[..., Dict[str, Any]]):
        """Attach a bounded application-service tool to this shared registry."""
        if not isinstance(tool_def, ToolDefinition) or not callable(handler):
            raise TypeError("external tools require a ToolDefinition and callable handler")
        if self._is_tool_enabled(tool_def.name):
            self._tools[tool_def.name] = {
                'def': tool_def,
                'skill': None,
                'handler': handler,
            }

    def _is_tool_enabled(self, tool_name: str) -> bool:
        if self.config is None:
            return True
        if hasattr(self.config, 'tool_enabled'):
            return self.config.tool_enabled(tool_name)
        if isinstance(self.config, dict):
            tools_config = self.config.get('tools', {})
            return tools_config.get(tool_name, True)
        return True

    @property
    def tools(self) -> Dict[str, Dict]:
        """Read-only-compatible view used by legacy runtimes."""
        return self._tools

    def permission_decision(self, tool_name: str) -> str:
        """Return allow/ask/deny from the configured permission policy."""
        permissions = self.config.get("permissions", {}) if isinstance(self.config, dict) else None
        if permissions is None and self.config is not None:
            getter = getattr(self.config, "get", None)
            permissions = getter("permissions", {}) if callable(getter) else {}
        permissions = permissions if isinstance(permissions, dict) else {}

        def matches(patterns) -> bool:
            return any(fnmatch.fnmatch(tool_name, str(pattern)) for pattern in (patterns or []))

        if matches(permissions.get("deny")):
            return "deny"
        if matches(permissions.get("allow")):
            return "allow"
        if matches(permissions.get("ask")):
            return "ask"
        mode = str(permissions.get("mode", "allow")).lower()
        return mode if mode in {"allow", "ask", "deny"} else "allow"

    def _validate_arguments(self, tool_name: str, params: Dict[str, Any]) -> None:
        definition = self.get_tool_def(tool_name)
        if definition is None:
            return
        schema = definition.parameters or {}
        for key, field in schema.items():
            if not isinstance(field, dict):
                continue
            if field.get("required") and key not in params:
                raise ValueError(f"{key} is required")
            if key not in params:
                continue
            expected = str(field.get("type", "")).lower()
            value = params[key]
            if expected in {"int", "integer"} and (not isinstance(value, int) or isinstance(value, bool)):
                raise TypeError(f"{key} must be an integer")
            if expected in {"float", "number"} and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                raise TypeError(f"{key} must be a number")
            if expected in {"str", "string"} and not isinstance(value, str):
                raise TypeError(f"{key} must be a string")
            if field.get("minimum") is not None and value < field["minimum"]:
                raise ValueError(f"{key} is below the minimum")
            if field.get("maximum") is not None and value > field["maximum"]:
                raise ValueError(f"{key} is above the maximum")

    def unregister_skill(self, skill_name: str):
        """注销一个技能及其工具"""
        if skill_name in self._skills:
            skill = self._skills.pop(skill_name)
            for tool_def in skill.get_tools():
                self._tools.pop(tool_def.name, None)

    def list_tools(self) -> List[Dict]:
        """列出所有可用工具（供 LLM 选择）"""
        return [
            {
                'name': t['def'].name,
                'description': t['def'].description,
                'parameters': t['def'].parameters,
                'skill': t['def'].skill,
            }
            for t in self._tools.values()
        ]

    def get_tool_def(self, tool_name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        if tool_name in self._tools:
            return self._tools[tool_name]['def']
        return None

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def call(self, tool_name: str, **params) -> Dict[str, Any]:
        """调用工具

        Returns:
            工具执行结果字典
        """
        start = time.time()

        if tool_name not in self._tools:
            result = {'error': f'Tool not found: {tool_name}', 'tool': tool_name}
            if self.memory:
                self.memory.log_tool_call(tool_name, params, result, False, 0)
            return result

        registered = self._tools[tool_name]
        confirmed = bool(params.pop("_confirmed", False))
        decision = self.permission_decision(tool_name)
        if decision == "deny":
            result = {"error": "permission denied", "tool": tool_name, "authorization": "deny"}
            if self.memory:
                self.memory.log_tool_call(tool_name, params, result, False, 0)
            return result
        if decision == "ask" and not confirmed:
            result = {"error": "confirmation required", "tool": tool_name, "authorization": "ask"}
            if self.memory:
                self.memory.log_tool_call(tool_name, params, result, False, 0)
            return result
        try:
            self._validate_arguments(tool_name, params)
        except (TypeError, ValueError) as exc:
            result = {"error": str(exc), "tool": tool_name, "error_code": exc.__class__.__name__}
            if self.memory:
                self.memory.log_tool_call(tool_name, params, result, False, 0)
            return result
        external_handler = registered.get('handler')
        if external_handler is not None:
            try:
                result = external_handler(**params)
            except TypeError:
                result = external_handler(params)
            duration_ms = (time.time() - start) * 1000
            if self.memory:
                self.memory.log_tool_call(tool_name, params, result, 'error' not in result, duration_ms)
            return result

        skill = registered['skill']
        try:
            result = skill.execute(tool_name, **params)
            success = 'error' not in result
        except Exception as e:
            result = {'error': str(e), 'tool': tool_name}
            success = False

        duration_ms = (time.time() - start) * 1000
        if self.memory:
            self.memory.log_tool_call(tool_name, params, result, success, duration_ms)
            self.memory.log_audit('tool_call', tool_name, params, str(result)[:200])

        return result

    async def call_async(self, tool_name: str, *, timeout: float = 30.0, retries: int = 0, **params) -> Dict[str, Any]:
        """Run synchronous skill handlers off-loop with bounded timeout/retry."""
        last = None
        for attempt in range(max(0, int(retries)) + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.call, tool_name, **params),
                    timeout=max(0.1, float(timeout)),
                )
            except asyncio.TimeoutError:
                last = {"error": "tool execution timed out", "tool": tool_name, "error_code": "timeout"}
            except Exception as exc:
                last = {"error": str(exc), "tool": tool_name, "error_code": exc.__class__.__name__}
            if attempt < max(0, int(retries)):
                await asyncio.sleep(min(2.0, 0.1 * (2 ** attempt)))
        return last or {"error": "tool execution failed", "tool": tool_name}

    @property
    def skills(self) -> List[str]:
        return list(self._skills.keys())

    @property
    def tool_count(self) -> int:
        return len(self._tools)
