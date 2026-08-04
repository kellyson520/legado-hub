"""
统一日志基础设施
- 结构化 JSON 日志（便于日志收集系统解析）
- 自动记录上下文（trace_id, module, user_id）
- 文件轮转 + 控制台输出
- 所有模块通过 get_logger(module_name) 获取统一格式的 logger
"""

import logging
import logging.handlers
import re
from contextvars import ContextVar
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_REDACTED = "***REDACTED***"
_SENSITIVE_KEY_PARTS = (
    "authorization", "api_key", "apikey", "access_token", "refresh_token",
    "password", "secret", "cookie", "private_key", "credential", "token",
)
_SAFE_IDENTIFIER_KEYS = {"api_key_id", "user_id", "trace_id", "session_id"}
_EXTRA_FIELDS = (
    "duration_ms", "status_code", "source_url", "action", "resource_type",
    "resource_id", "method", "path", "operation", "agent_kind", "tool_name",
    "error_code", "api_key_id", "user_id",
)
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"password|secret|cookie|private[_-]?key|credential|token)\b(\s*[:=]\s*)"
    r"(?:Bearer\s+)?([^\s,;]+)"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/-]+)")
_RAW_CREDENTIAL_RE = re.compile(r"\b(?:lh_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+)\b")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized not in _SAFE_IDENTIFIER_KEYS and any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_url(value: str) -> str:
    """Mask sensitive query-string values while retaining safe diagnostics."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    query = parse_qsl(parsed.query, keep_blank_values=True)
    has_sensitive_query = any(_is_sensitive_key(key) for key, _ in query)
    has_credentials = parsed.username is not None or parsed.password is not None
    if not has_sensitive_query and not has_credentials:
        return value
    netloc = parsed.netloc
    if has_credentials:
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port = f":{parsed.port}" if parsed.port is not None else ""
        except ValueError:
            port = ""
        netloc = f"{_REDACTED}@{host}{port}"
    return urlunsplit(
        (parsed.scheme, netloc, parsed.path, urlencode([
            (key, _REDACTED if _is_sensitive_key(key) else item)
            for key, item in query
        ]), parsed.fragment)
    )


def redact_sensitive_data(value: Any) -> Any:
    """Return a safe copy suitable for logs without changing normal identifiers."""
    if isinstance(value, dict):
        return {
            key: _REDACTED if _is_sensitive_key(str(key)) else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if not isinstance(value, str):
        return value
    redacted = _ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", value)
    redacted = _BEARER_TOKEN_RE.sub(lambda match: f"{match.group(1)}{_REDACTED}", redacted)
    redacted = _RAW_CREDENTIAL_RE.sub(_REDACTED, redacted)
    return _redact_url(redacted)


_log_context: ContextVar[dict[str, Any]] = ContextVar("legado_log_context", default={})


class _LogContextProxy:
    """Compatibility facade with ContextVar-backed values for legacy callers."""

    def __getattr__(self, name: str) -> Any:
        return _log_context.get().get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        values = dict(_log_context.get())
        if value is None:
            values.pop(name, None)
        else:
            values[name] = value
        _log_context.set(values)


# Kept as a module attribute so existing integrations can read context fields.
_context = _LogContextProxy()

def resolve_log_dir(base_dir: str | os.PathLike[str] | None = None) -> Path:
    """Return a writable-by-default log directory for local and container runs."""
    configured = os.environ.get("LOG_DIR", "").strip()
    if configured:
        return Path(configured)
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[2]
    return root / "logs"


LOG_DIR = resolve_log_dir()
os.makedirs(LOG_DIR, exist_ok=True)


class JSONFormatter(logging.Formatter):
    """JSON 结构化日志格式器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
            "module": getattr(record, "module_tag", record.module),
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加上下文信息
        trace_id = _context.trace_id
        if trace_id:
            log_obj["trace_id"] = trace_id
        
        user_id = _context.user_id
        if user_id:
            log_obj["user_id"] = user_id
        
        api_key_id = _context.api_key_id
        if api_key_id:
            log_obj["api_key_id"] = api_key_id
        
        # 异常信息
        if record.exc_info:
            log_obj["exception"] = redact_sensitive_data(self.formatException(record.exc_info))
        
        # 额外字段
        for key in _EXTRA_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = redact_sensitive_data(val)
        
        return json.dumps(log_obj, ensure_ascii=False, default=str)


class ContextAdapter(logging.LoggerAdapter):
    """带上下文的日志适配器"""
    
    def process(self, msg, kwargs):
        extra = dict(kwargs.get("extra") or {})
        # 将上下文注入 extra，由 formatter 读取
        trace_id = _context.trace_id
        if trace_id:
            extra["trace_id"] = trace_id
        user_id = _context.user_id
        if user_id:
            extra["user_id"] = user_id
        kwargs["extra"] = extra
        return msg, kwargs


class SecretRedactionFilter(logging.Filter):
    """Apply the same masking rule to JSON and human-readable handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_legado_redacted", False):
            return True
        record.msg = redact_sensitive_data(record.getMessage())
        record.args = ()
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                setattr(record, key, redact_sensitive_data(getattr(record, key)))
        record._legado_redacted = True
        return True


class RedactingTextFormatter(logging.Formatter):
    """Ensure exception text is safe when structured logs are disabled."""

    def format(self, record: logging.LogRecord) -> str:
        return str(redact_sensitive_data(super().format(record)))


def setup_logging(
    level: str = "INFO",
    enable_json: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
):
    """
    初始化全局日志配置
    
    Args:
        level: 日志级别 DEBUG/INFO/WARNING/ERROR
        enable_json: 是否使用 JSON 格式（生产环境建议开启）
        max_bytes: 单个日志文件大小上限
        backup_count: 保留的备份文件数
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # 清除已有 handler
    for h in root.handlers[:]:
        root.removeHandler(h)
    
    # 格式化器
    if enable_json:
        formatter = JSONFormatter()
    else:
        formatter = RedactingTextFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
    
    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(SecretRedactionFilter())
    root.addHandler(console)
    
    # 文件 handler（按大小轮转）
    app_file = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    app_file.setFormatter(formatter)
    app_file.addFilter(SecretRedactionFilter())
    root.addHandler(app_file)
    
    # 错误日志单独文件
    error_file = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)
    error_file.addFilter(SecretRedactionFilter())
    root.addHandler(error_file)
    
    # 降低第三方库日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    root.info(f"[Logging] 日志系统初始化完成, 级别={level}, JSON={enable_json}", extra={"action": "logging_initialized"})


def get_logger(name: str) -> ContextAdapter:
    """
    获取带模块标识的统一 logger
    
    Usage:
        logger = get_logger("source_manager")
        logger.info("拉取订阅完成", extra={"action": "fetch", "source_url": "..."})
    """
    logger = logging.getLogger(name)
    return ContextAdapter(logger, {})


# ============ 上下文管理 ============

def set_log_context(trace_id: Optional[str] = None, user_id: Optional[str] = None, api_key_id: Optional[int] = None):
    """Set request-scoped context without leaking values into sibling coroutines."""
    values = dict(_log_context.get())
    if trace_id is not None:
        values["trace_id"] = trace_id
    if user_id is not None:
        values["user_id"] = user_id
    if api_key_id is not None:
        values["api_key_id"] = api_key_id
    _log_context.set(values)


def clear_log_context():
    """Clear the current coroutine's log context."""
    _log_context.set({})


def get_trace_id() -> Optional[str]:
    return _context.trace_id
