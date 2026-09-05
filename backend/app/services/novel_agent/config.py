"""
Agent 配置管理 - 参考 DeepSeek-Reasonix 的 config-driven 设计

所有技能、工具、模型参数都通过配置文件声明，无硬编码。
支持 TOML/JSON 格式，优先级：环境变量 > 项目配置 > 默认值。
"""

import os
import json
from typing import Any, Dict, Optional, List
from pathlib import Path

from app.core.logging import get_logger

from .providers import ProviderConfig


class AgentConfigError(ValueError):
    """Raised when an explicit Agent configuration cannot be loaded."""


logger = get_logger(__name__)


class AgentConfig:
    """Agent 配置管理器

    设计原则（参考 Reasonix）：
    - 配置即契约：所有行为由配置声明
    - 分层覆盖：环境变量 > 项目配置 > 用户配置 > 默认值
    - 类型安全：配置键路径访问，默认值兜底
    """

    DEFAULT_CONFIG: Dict[str, Any] = {
        'agent': {
            'name': 'NovelAgent',
            'version': '2.0.0',
            'default_model': 'deepseek-flash',
            'planner_model': '',
            'planner_max_steps': 5,
            'max_iterations': 20,
            'max_tool_calls_per_step': 5,
            'think_verbose': True,
            'enable_mcp': False,
            'compact_ratio': 0.8,
            'recent_keep': 8,
            'effort': 'auto',
        },
        'providers': [
            {
                'name': 'deepseek-flash',
                'kind': 'openai',
                'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-chat',
                'api_key_env': 'DEEPSEEK_API_KEY',
                'context_window': 128000,
            },
            {
                'name': 'deepseek-pro',
                'kind': 'openai',
                'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-pro',
                'api_key_env': 'DEEPSEEK_API_KEY',
                'context_window': 128000,
            },
        ],
        'llm': {
            'provider': 'mock',
            'model': 'deepseek-v3',
            'base_url': '',
            'api_key': '',
            'api_key_env': 'LLM_API_KEY',
            'temperature': 0.7,
            'max_tokens': 4096,
            'system_prompt': '',
        },
        'skills': {
            'source': True,
            'collector': True,
            'extractor': True,
            'auditor': True,
            'grapher': True,
            'qa': True,
            'summarizer': True,
            'writer': True,
            'reasoner': True,
            'ocr': True,
        },
        'tools': {
            'recall_context': True,
            'extract_evidence': True,
            'detect_conflicts': True,
            'trace_reasoning': True,
            'verify_alias': True,
            'search_pattern': True,
            'propose_correction': True,
            'plot_search': True,
            'chapter_summary': True,
            'character_timeline': True,
            'community_query': True,
            'graph_stats': True,
            'generate_graph_html': True,
            'ocr_recognize': True,
            'ocr_extract_text': True,
            'ocr_translate': True,
        },
        'memory': {
            'sqlite_path': 'data/novel_agent.db',
            'max_history': 100,
            'enable_project_memory': True,
            'project_memory_file': '.novel_agent/AGENTS.md',
        },
        'novel': {
            'name': '',
            'data_dir': 'data/novels',
            'graph_file': 'data/graph.json',
            'default_book_url': '',
        },
        'mcp': {
            'servers': [],
            'timeout': 30,
        },
        'ocr': {
            'backend': 'paddleocr',
            'lang': 'ch_sim+en',
            'enable_translation': True,
            'translation_target': 'zh',
        },
        'permissions': {
            'mode': 'ask',
            'allow': [],
            'ask': [],
            'deny': [],
        },
    }

    def __init__(self, config_path: Optional[str] = None, config_dict: Optional[Dict] = None):
        self._config = self._deep_copy(self.DEFAULT_CONFIG)
        if config_dict:
            self._deep_update(self._config, config_dict)
        if config_path:
            self._load_file(config_path)
        self._load_env_overrides()

    def _deep_copy(self, d: Dict) -> Dict:
        return json.loads(json.dumps(d))

    def _deep_update(self, base: Dict, override: Dict):
        for k, v in override.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _load_file(self, path: str):
        p = Path(path)
        if not p.exists():
            raise AgentConfigError(f"configuration file not found: {p}")
        suffix = p.suffix.lower()
        try:
            if suffix in ('.json',):
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._deep_update(self._config, data)
            elif suffix in ('.toml',):
                try:
                    import tomllib
                except ImportError as exc:
                    try:
                        import tomli as tomllib
                    except ImportError:
                        raise AgentConfigError("TOML support is unavailable on this Python runtime") from exc
                with open(p, 'rb') as f:
                    data = tomllib.load(f)
                self._deep_update(self._config, data)
            else:
                raise AgentConfigError(f"unsupported configuration format: {p.suffix or '<none>'}")
        except AgentConfigError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            logger.error("failed to load Agent configuration %s: %s", p, exc)
            raise AgentConfigError(f"failed to load configuration {p}: {exc}") from exc

    def _load_env_overrides(self):
        env_map = {
            'LLM_PROVIDER': 'llm.provider',
            'LLM_MODEL': 'llm.model',
            'LLM_BASE_URL': 'llm.base_url',
            'LLM_API_KEY': 'llm.api_key',
            'DEEPSEEK_API_KEY': 'llm.api_key',
            'NOVEL_NAME': 'novel.name',
            'NOVEL_DATA_DIR': 'novel.data_dir',
            'DEFAULT_MODEL': 'agent.default_model',
        }
        for env_key, config_key in env_map.items():
            val = os.environ.get(env_key)
            if val:
                self.set(config_key, val)

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        v = self._config
        for k in keys:
            if isinstance(v, dict) and k in v:
                v = v[k]
            else:
                return default
        return v

    def set(self, key: str, value: Any):
        keys = key.split('.')
        d = self._config
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def skill_enabled(self, skill_name: str) -> bool:
        return bool(self.get(f'skills.{skill_name}', False))

    def tool_enabled(self, tool_name: str) -> bool:
        return bool(self.get(f'tools.{tool_name}', True))

    def to_dict(self) -> Dict:
        return self._deep_copy(self._config)

    def get_provider_configs(self) -> List[ProviderConfig]:
        """获取所有 Provider 配置"""
        providers = self.get('providers', [])
        result = []
        for p in providers:
            result.append(ProviderConfig(
                name=p.get('name', ''),
                kind=p.get('kind', 'openai'),
                base_url=p.get('base_url', ''),
                model=p.get('model', ''),
                api_key_env=p.get('api_key_env', ''),
                api_key=p.get('api_key', ''),
                context_window=p.get('context_window', 128000),
                extra=p.get('extra', {}),
            ))
        return result

    def resolve_model(self, model_ref: Optional[str] = None) -> ProviderConfig:
        """解析模型引用，返回对应的 ProviderConfig"""
        if not model_ref:
            model_ref = self.get('agent.default_model', 'deepseek-flash')

        for p in self.get_provider_configs():
            if p.name == model_ref or p.model == model_ref:
                return p

        return self.get_provider_configs()[0] if self.get_provider_configs() else ProviderConfig(
            name='default',
            kind='openai',
            base_url='https://api.deepseek.com',
            model='deepseek-chat',
            api_key_env='DEEPSEEK_API_KEY',
        )

    @classmethod
    def from_project(cls, project_dir: str = '.') -> 'AgentConfig':
        config_paths = [
            os.path.join(project_dir, 'novel_agent.toml'),
            os.path.join(project_dir, 'novel_agent.json'),
            os.path.join(project_dir, '.novel_agent', 'config.json'),
        ]
        for p in config_paths:
            if os.path.exists(p):
                return cls(config_path=p)
        return cls()
