"""当前异常体系与 FastAPI 异常处理器的契约测试。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.exception_handlers import (
    app_exception_handler,
    generic_exception_handler,
    register_exception_handlers,
    validation_exception_handler,
)
from app.core.exceptions import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    ValidationException,
)


@pytest.fixture
def request_factory():
    """创建带可控 debug 与 trace_id 的实际 Starlette Request。"""

    def build(*, debug: bool = False, trace_id: str | None = "trace-test") -> Request:
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/test/path",
                "raw_path": b"/test/path",
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
                "app": FastAPI(debug=debug),
                "state": {},
            }
        )
        if trace_id is not None:
            request.state.trace_id = trace_id
        return request

    return build


def response_body(response) -> dict:
    """解析 JSONResponse 的响应内容。"""

    return json.loads(response.body.decode())


class TestAppException:
    def test_app_exception_preserves_constructor_contract(self):
        details = {"field": "name"}

        exc = AppException("TEST_ERROR", "test message", 418, details)

        assert isinstance(exc, Exception)
        assert str(exc) == "test message"
        assert exc.code == "TEST_ERROR"
        assert exc.message == "test message"
        assert exc.status_code == 418
        assert exc.details == details

    def test_app_exception_defaults_details_to_empty_dict(self):
        exc = AppException("TEST_ERROR", "test message", 500)

        assert exc.details == {}

    @pytest.mark.parametrize(
        ("exception_type", "status_code", "code", "message"),
        [
            (AuthenticationException, 401, "AUTHENTICATION_ERROR", "authentication failed"),
            (AuthorizationException, 403, "AUTHORIZATION_ERROR", "permission denied"),
            (ValidationException, 422, "VALIDATION_ERROR", "validation failed"),
            (NotFoundException, 404, "NOT_FOUND", "resource not found"),
            (ConflictException, 409, "CONFLICT", "resource conflict"),
            (ExternalServiceException, 502, "EXTERNAL_SERVICE_ERROR", "external service failed"),
        ],
    )
    def test_concrete_exceptions_expose_current_contract(
        self,
        exception_type,
        status_code,
        code,
        message,
    ):
        exc = exception_type()

        assert isinstance(exc, AppException)
        assert exc.status_code == status_code
        assert exc.code == code
        assert exc.message == message
        assert exc.details == {}

    def test_concrete_exception_accepts_custom_message_and_details(self):
        exc = NotFoundException("source not found", {"source_id": 7})

        assert exc.message == "source not found"
        assert exc.details == {"source_id": 7}


class TestExceptionHandlers:
    async def test_app_exception_handler_returns_current_envelope(self, request_factory):
        response = await app_exception_handler(
            request_factory(),
            NotFoundException("source not found", {"source_id": 7}),
        )

        assert response.status_code == 404
        assert response_body(response) == {
            "success": False,
            "code": "NOT_FOUND",
            "message": "source not found",
            "details": {"source_id": 7},
            "trace_id": "trace-test",
        }

    async def test_validation_exception_handler_preserves_validation_errors(self, request_factory):
        errors = [
            {
                "loc": ("body", "name"),
                "msg": "Field required",
                "type": "missing",
            }
        ]
        response = await validation_exception_handler(
            request_factory(),
            RequestValidationError(errors),
        )

        assert response.status_code == 422
        assert response_body(response) == {
            "success": False,
            "code": "VALIDATION_ERROR",
            "message": "validation failed",
            "details": {
                "errors": [
                    {
                        "loc": ["body", "name"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            },
            "trace_id": "trace-test",
        }

    async def test_generic_exception_handler_hides_message_when_debug_is_disabled(self, request_factory):
        response = await generic_exception_handler(
            request_factory(debug=False),
            RuntimeError("secret diagnostic"),
        )

        assert response.status_code == 500
        assert response_body(response) == {
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": "internal server error",
            "details": {},
            "trace_id": "trace-test",
        }

    async def test_generic_exception_handler_exposes_message_when_debug_is_enabled(self, request_factory):
        response = await generic_exception_handler(
            request_factory(debug=True, trace_id=None),
            RuntimeError("debug diagnostic"),
        )

        assert response.status_code == 500
        assert response_body(response) == {
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": "debug diagnostic",
            "details": {},
            "trace_id": None,
        }


class TestRegisterExceptionHandlers:
    def test_register_exception_handlers_registers_current_exception_classes(self):
        app = FastAPI()

        register_exception_handlers(app)

        assert app.exception_handlers[AppException] is app_exception_handler
        assert app.exception_handlers[RequestValidationError] is validation_exception_handler
        assert app.exception_handlers[Exception] is generic_exception_handler
