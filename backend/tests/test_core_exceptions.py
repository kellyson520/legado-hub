"""
exceptions.py 单元测试

覆盖异常类和全局异常处理器：
- 各异常类的属性验证（status_code, error_code, default_message）
- 异常消息和详情的自定义
- register_exception_handlers 注册 3 个处理器
- 异常处理器的响应格式
"""

import pytest
from unittest.mock import MagicMock, patch


class TestBaseAppException:
    """BaseAppException 基础异常测试"""

    def test_default_attributes(self):
        """验证默认属性值"""
        from app.core.exceptions import BaseAppException
        exc = BaseAppException()
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.message == "内部错误"
        assert exc.details == {}

    def test_custom_message(self):
        """验证自定义消息"""
        from app.core.exceptions import BaseAppException
        exc = BaseAppException(message="自定义内部错误")
        assert exc.message == "自定义内部错误"

    def test_custom_details(self):
        """验证自定义详情"""
        from app.core.exceptions import BaseAppException
        details = {"field": "username", "issue": "已存在"}
        exc = BaseAppException(message="冲突", details=details)
        assert exc.details == details

    def test_is_exception_subclass(self):
        """验证继承自 Exception"""
        from app.core.exceptions import BaseAppException
        assert issubclass(BaseAppException, Exception)

    def test_str_representation(self):
        """验证异常的字符串表示为 message"""
        from app.core.exceptions import BaseAppException
        exc = BaseAppException(message="测试错误")
        assert str(exc) == "测试错误"


class TestConcreteExceptions:
    """具体异常子类测试"""

    @pytest.mark.parametrize("exc_class,expected_status,expected_code,expected_msg", [
        ("ValidationException", 400, "VALIDATION_ERROR", "请求参数错误"),
        ("AuthenticationException", 401, "AUTHENTICATION_ERROR", "认证失败"),
        ("AuthorizationException", 403, "AUTHORIZATION_ERROR", "权限不足"),
        ("NotFoundException", 404, "NOT_FOUND", "资源不存在"),
        ("QuotaExceededException", 429, "QUOTA_EXCEEDED", "配额已用完"),
        ("ExternalServiceException", 502, "EXTERNAL_SERVICE_ERROR", "外部服务暂不可用"),
    ])
    def test_exception_attributes(self, exc_class, expected_status, expected_code, expected_msg):
        """参数化验证各异常子类的默认属性"""
        import app.core.exceptions as exc_module
        cls = getattr(exc_module, exc_class)
        exc = cls()
        assert exc.status_code == expected_status
        assert exc.error_code == expected_code
        assert exc.message == expected_msg

    def test_quota_exceeded_custom_message(self):
        """验证 QuotaExceededException 自定义消息"""
        from app.core.exceptions import QuotaExceededException
        exc = QuotaExceededException(message="每日配额已用完", details={"limit": 500, "used": 500})
        assert exc.message == "每日配额已用完"
        assert exc.details["limit"] == 500

    def test_not_found_custom_message(self):
        """验证 NotFoundException 自定义消息"""
        from app.core.exceptions import NotFoundException
        exc = NotFoundException(message="书源不存在")
        assert exc.message == "书源不存在"
        assert exc.status_code == 404


class TestExceptionHandlers:
    """全局异常处理器测试"""

    async def test_app_exception_handler_returns_json_response(self, mock_request):
        """验证 app_exception_handler 返回正确格式的 JSONResponse"""
        from app.core.exceptions import app_exception_handler, NotFoundException
        import json
        exc = NotFoundException(message="测试资源不存在")
        response = await app_exception_handler(mock_request, exc)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["success"] is False
        assert body["code"] == "NOT_FOUND"
        assert body["message"] == "测试资源不存在"
        assert body["path"] == "/test/path"

    async def test_app_exception_handler_includes_details(self, mock_request):
        """验证 app_exception_handler 包含 details 字段"""
        from app.core.exceptions import app_exception_handler, ValidationException
        import json
        exc = ValidationException(message="校验失败", details={"field": "name"})
        response = await app_exception_handler(mock_request, exc)
        body = json.loads(response.body.decode())
        assert body["details"] == {"field": "name"}

    async def test_generic_exception_handler(self, mock_request):
        """验证 generic_exception_handler 处理未捕获异常"""
        from app.core.exceptions import generic_exception_handler
        import json
        exc = RuntimeError("意外错误")
        response = await generic_exception_handler(mock_request, exc)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["code"] == "INTERNAL_ERROR"
        assert body["message"] == "服务器内部错误"

    async def test_validation_exception_handler_with_errors(self, mock_request):
        """验证 validation_exception_handler 正确提取 FastAPI 校验错误"""
        from app.core.exceptions import validation_exception_handler
        import json

        # 模拟 FastAPI RequestValidationError
        exc = MagicMock()
        exc.errors.return_value = [
            {"loc": ("body", "name"), "msg": "字段必填", "type": "value_error.missing"}
        ]
        response = await validation_exception_handler(mock_request, exc)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["code"] == "VALIDATION_ERROR"
        assert len(body["details"]["errors"]) == 1
        assert body["details"]["errors"][0]["field"] == "body.name"


class TestRegisterExceptionHandlers:
    """register_exception_handlers 注册测试"""

    def test_register_exception_handlers_adds_three_handlers(self):
        """验证 register_exception_handlers 注册了 3 个处理器"""
        from app.core.exceptions import (
            register_exception_handlers, BaseAppException
        )
        from fastapi import FastAPI
        from fastapi.exceptions import RequestValidationError

        app = FastAPI()
        register_exception_handlers(app)

        # 验证注册的异常处理器
        assert BaseAppException in app.exception_handlers
        assert RequestValidationError in app.exception_handlers
        assert Exception in app.exception_handlers
