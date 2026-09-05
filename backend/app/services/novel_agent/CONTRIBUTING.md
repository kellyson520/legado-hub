# 贡献指南

## 代码规范

### 命名规范

- **模块/包**: 小写 + 下划线 (`novel_agent`, `reasonix_agent`)
- **类**: PascalCase (`NovelAgent`, `ToolRegistry`)
- **方法/函数**: snake_case (`run`, `find_relation`)
- **常量**: UPPER_SNAKE_CASE (`DEFAULT_CONFIG`, `SYSTEM_PROMPT`)
- **私有方法**: 前缀下划线 (`_compact_if_needed`)

### 类型注解

所有公共方法必须标注类型：

```python
from typing import Dict, List, Optional, Any

def run(self, goal: str, max_iterations: Optional[int] = None) -> AgentResponse:
    ...
```

### 文档字符串

所有公共类/方法使用 Google 风格 docstring：

```python
def find_relation(self, char1: str, char2: str) -> Dict[str, Any]:
    """查找两个人物之间的关系。

    Args:
        char1: 第一个人物名称
        char2: 第二个人物名称

    Returns:
        包含关系信息的字典，格式为:
        {
            'found': bool,
            'char1': str,
            'char2': str,
            'type': str,
            'description': str,
            'confidence': float
        }
    """
```

### 错误处理

- 工具执行失败返回包含 `error` 键的字典，不抛异常
- 内部错误使用日志记录，不暴露给用户
- 关键错误在 AgentResponse 中标记 `success=False`

### 配置驱动

**禁止硬编码**。所有行为参数通过 [config.py](config.py) 获取：

```python
# ✅ 正确
max_iter = self.config.get('agent.max_iterations', 20)

# ❌ 错误
MAX_ITERATIONS = 20
```

### 接口契约

新增组件必须实现对应接口：

- **Skill** → 继承 `BaseSkill`
- **Tool** → 继承 `BaseTool`
- **Provider** → 继承 `BaseProvider`

### 测试要求

- 新增工具/技能必须附带单元测试
- 测试放在 `tests/` 目录，命名 `test_<component>.py`
- 使用 `pytest` 框架

## 提交流程

1. 创建功能分支：`feature/xxx` 或 `fix/xxx`
2. 遵循代码规范
3. 运行测试：`pytest tests/`
4. 更新 [ARCHITECTURE.md](ARCHITECTURE.md)
5. 提交 PR，描述变更动机和影响范围
