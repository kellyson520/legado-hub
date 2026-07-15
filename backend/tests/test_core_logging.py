"""
logging.py 单元测试

覆盖日志模块的核心功能：
- setup_logging 初始化
- get_logger 获取 logger
- set_log_context / clear_log_context 上下文管理
- get_trace_id 获取追踪 ID
- ContextAdapter 上下文注入
- JSONFormatter 格式化输出
"""

import logging
import json
import io
import asyncio
from unittest.mock import patch, MagicMock

import pytest


class TestGetLogger:
    """get_logger 函数测试"""

    def test_get_logger_returns_context_adapter(self):
        """验证 get_logger 返回 ContextAdapter 实例"""
        from app.core.logging import get_logger
        logger = get_logger("test_module")
        # ContextAdapter 继承自 LoggerAdapter
        assert hasattr(logger, "process")

    def test_get_logger_with_different_names(self):
        """验证不同名称获取不同 logger"""
        from app.core.logging import get_logger
        logger_a = get_logger("module_a")
        logger_b = get_logger("module_b")
        assert logger_a.logger.name == "module_a"
        assert logger_b.logger.name == "module_b"

    def test_get_logger_same_name_returns_same_logger(self):
        """验证相同名称返回相同 logger"""
        from app.core.logging import get_logger
        logger1 = get_logger("same_module")
        logger2 = get_logger("same_module")
        assert logger1.logger is logger2.logger


class TestLogContext:
    """日志上下文管理测试"""

    def test_set_log_context_trace_id(self):
        """验证设置 trace_id 上下文"""
        from app.core.logging import set_log_context, get_trace_id
        set_log_context(trace_id="trace-abc-123")
        assert get_trace_id() == "trace-abc-123"

    def test_set_log_context_multiple_fields(self):
        """验证同时设置多个上下文字段"""
        from app.core.logging import set_log_context, clear_log_context, _context
        set_log_context(trace_id="trace-001", user_id="user-42", api_key_id=7)
        assert _context.trace_id == "trace-001"
        assert _context.user_id == "user-42"
        assert _context.api_key_id == 7

    def test_clear_log_context(self):
        """验证清除上下文后所有字段为 None"""
        from app.core.logging import set_log_context, clear_log_context, get_trace_id
        set_log_context(trace_id="trace-001", user_id="user-42")
        clear_log_context()
        assert get_trace_id() is None

    def test_get_trace_id_without_context(self):
        """验证未设置上下文时 get_trace_id 返回 None"""
        from app.core.logging import clear_log_context, get_trace_id
        clear_log_context()
        assert get_trace_id() is None

    @pytest.mark.asyncio
    async def test_log_context_is_isolated_between_concurrent_tasks(self):
        """并发请求的 trace 上下文不能在同一线程内相互覆盖。"""
        from app.core.logging import clear_log_context, get_trace_id, set_log_context

        async def read_own_trace(trace_id: str) -> str | None:
            set_log_context(trace_id=trace_id)
            await asyncio.sleep(0)
            value = get_trace_id()
            clear_log_context()
            return value

        first, second = await asyncio.gather(
            read_own_trace("request-a"),
            read_own_trace("request-b"),
        )

        assert first == "request-a"
        assert second == "request-b"


class TestContextAdapter:
    """ContextAdapter 日志适配器测试"""

    def test_context_adapter_injects_trace_id(self):
        """验证 ContextAdapter 自动注入 trace_id 到日志 extra"""
        from app.core.logging import get_logger, set_log_context, clear_log_context
        set_log_context(trace_id="inject-test-trace")

        logger = get_logger("adapter_test")
        msg, kwargs = logger.process("test message", {"extra": {}})
        assert kwargs["extra"]["trace_id"] == "inject-test-trace"

        clear_log_context()

    def test_context_adapter_injects_user_id(self):
        """验证 ContextAdapter 自动注入 user_id 到日志 extra"""
        from app.core.logging import get_logger, set_log_context, clear_log_context
        set_log_context(user_id="user-999")

        logger = get_logger("adapter_test")
        msg, kwargs = logger.process("test message", {"extra": {}})
        assert kwargs["extra"]["user_id"] == "user-999"

        clear_log_context()


class TestJSONFormatter:
    """JSONFormatter 格式化器测试"""

    def test_json_formatter_output_is_valid_json(self):
        """验证格式化输出为合法 JSON"""
        from app.core.logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="测试消息", args=None, exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "测试消息"
        assert parsed["level"] == "INFO"

    def test_json_formatter_includes_trace_id_from_context(self):
        """验证 JSONFormatter 包含 trace_id（从线程本地上下文）"""
        from app.core.logging import JSONFormatter, _context
        formatter = JSONFormatter()
        _context.trace_id = "json-trace-001"

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="消息", args=None, exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "json-trace-001"
        _context.trace_id = None

    def test_json_formatter_omits_trace_id_when_absent(self):
        """验证无 trace_id 时不包含该字段"""
        from app.core.logging import JSONFormatter, _context
        formatter = JSONFormatter()
        _context.trace_id = None

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="消息", args=None, exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "trace_id" not in parsed

    def test_json_formatter_includes_exception_info(self):
        """验证 JSONFormatter 包含异常信息"""
        from app.core.logging import JSONFormatter
        import sys
        formatter = JSONFormatter()

        try:
            raise ValueError("测试异常")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="出错", args=None, exc_info=exc_info
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_json_formatter_redacts_credentials_from_messages_and_urls(self):
        """日志不能泄漏 Bearer、API key、Cookie 或 URL 查询令牌。"""
        from app.core.logging import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1,
            msg="Authorization: Bearer lh_live_secret_token password=hunter2 cookie=session-secret",
            args=None,
            exc_info=None,
        )
        record.source_url = "https://reader:redis-secret@example.test/chapter?access_token=token-secret&chapter=1"

        parsed = json.loads(formatter.format(record))

        serialized = json.dumps(parsed, ensure_ascii=False)
        assert "lh_live_secret_token" not in serialized
        assert "hunter2" not in serialized
        assert "session-secret" not in serialized
        assert "token-secret" not in serialized
        assert "redis-secret" not in serialized
        assert "***REDACTED***" in serialized


class TestSetupLogging:
    """setup_logging 初始化测试"""

    def test_setup_logging_configures_root_logger(self):
        """验证 setup_logging 配置根 logger"""
        from app.core.logging import setup_logging
        # 清除现有 handler
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)

        setup_logging(level="DEBUG", enable_json=False)
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1  # 至少有 console handler

        # 恢复
        root.handlers.clear()
