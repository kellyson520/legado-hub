class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationException(AppException):
    def __init__(self, message: str = "authentication failed", details: dict | None = None):
        super().__init__("AUTHENTICATION_ERROR", message, 401, details)


class AuthorizationException(AppException):
    def __init__(self, message: str = "permission denied", details: dict | None = None):
        super().__init__("AUTHORIZATION_ERROR", message, 403, details)


class ValidationException(AppException):
    def __init__(self, message: str = "validation failed", details: dict | None = None):
        super().__init__("VALIDATION_ERROR", message, 422, details)


class NotFoundException(AppException):
    def __init__(self, message: str = "resource not found", details: dict | None = None):
        super().__init__("NOT_FOUND", message, 404, details)


class ConflictException(AppException):
    def __init__(self, message: str = "resource conflict", details: dict | None = None):
        super().__init__("CONFLICT", message, 409, details)


class ExternalServiceException(AppException):
    def __init__(self, message: str = "external service failed", details: dict | None = None):
        super().__init__("EXTERNAL_SERVICE_ERROR", message, 502, details)
