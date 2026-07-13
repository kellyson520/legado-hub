"""
统一日志基础设施
- 结构化 JSON 日志（便于日志收集系统解析）
- 自动记录上下文（trace_id, module, user_id）
- 文件轮转 + 控制台输出
- 所有模块通过 get_logger(module_name) 获取统一格式的 logger
"""

import logging
import logging.handlers
import json
import sys
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

# 线程本地存储上下文
_context = threading.local()

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
os.makedirs(LOG_DIR, exist_ok=True)


class JSONFormatter(logging.Formatter):
    """JSON 结构化日志格式器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": getattr(record, "module_tag", record.module),
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加上下文信息
        trace_id = getattr(_context, "trace_id", None)
        if trace_id:
            log_obj["trace_id"] = trace_id
        
        user_id = getattr(_context, "user_id", None)
        if user_id:
            log_obj["user_id"] = user_id
        
        api_key_id = getattr(_context, "api_key_id", None)
        if api_key_id:
            log_obj["api_key_id"] = api_key_id
        
        # 异常信息
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # 额外字段
        for key in ["duration_ms", "status_code", "source_url", "action", "resource_type"]:
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = val
        
        return json.dumps(log_obj, ensure_ascii=False, default=str)


class ContextAdapter(logging.LoggerAdapter):
    """带上下文的日志适配器"""
    
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        # 将上下文注入 extra，由 formatter 读取
        trace_id = getattr(_context, "trace_id", None)
        if trace_id:
            extra["trace_id"] = trace_id
        user_id = getattr(_context, "user_id", None)
        if user_id:
            extra["user_id"] = user_id
        kwargs["extra"] = extra
        return msg, kwargs


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
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
    
    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)
    
    # 文件 handler（按大小轮转）
    app_file = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    app_file.setFormatter(formatter)
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
    root.addHandler(error_file)
    
    # 降低第三方库日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    root.info(f"[Logging] 日志系统初始化完成, 级别={level}, JSON={enable_json}")


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
    """设置当前线程的日志上下文"""
    if trace_id:
        _context.trace_id = trace_id
    if user_id:
        _context.user_id = user_id
    if api_key_id:
        _context.api_key_id = api_key_id


def clear_log_context():
    """清除当前线程的日志上下文"""
    _context.trace_id = None
    _context.user_id = None
    _context.api_key_id = None


def get_trace_id() -> Optional[str]:
    return getattr(_context, "trace_id", None)
