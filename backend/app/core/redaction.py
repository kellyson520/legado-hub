"""Shared redaction for data that may cross an agent or persistence boundary."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEY_PARTS = (
    "cookie",
    "token",
    "authorization",
    "bearer",
    "provider",
    "internal",
    "api_key",
    "apikey",
    "password",
    "secret",
    "credential",
    "header",
)
_SENSITIVE_QUERY_KEYS = frozenset({
    "token", "access_token", "api_key", "apikey", "authorization", "cookie", "password", "secret", "key",
})
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(\b(?:authorization|cookie|bearer|api[-_]?key|token|password|secret|credential)\b)"
    r"\s*(?:[:=]|\s+)\s*(?:(?:bearer|basic)\s+)?([^\s,;]+)"
)
_URL_PATTERN = re.compile(r"(?i)https?://[^\s<>\"']+")


def sanitize_for_boundary(value):
    """Recursively remove sensitive fields and redact credential-bearing strings."""
    if isinstance(value, list):
        return [sanitize_for_boundary(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_boundary(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): sanitize_for_boundary(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, str):
        return _redact_string(value)
    return value


def sanitize_error(value: object, *, limit: int = 500) -> str:
    """Return a bounded exception message safe for APIs, agents and storage."""

    raw_message = str(value)
    message = _URL_PATTERN.sub(
        lambda match: str(sanitize_for_boundary(match.group(0))),
        raw_message,
    )
    message = sanitize_for_boundary(message)
    return str(message)[:limit] or value.__class__.__name__


def _redact_string(value: str) -> str:
    redacted = _CREDENTIAL_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", value)
    try:
        parsed = urlsplit(redacted)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            netloc = parsed.hostname
            if parsed.port is not None:
                netloc = f"{netloc}:{parsed.port}"
            query = [
                (key, "[redacted]" if key.lower() in _SENSITIVE_QUERY_KEYS else item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            ]
            redacted = urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), ""))
    except (ValueError, TypeError):
        pass
    return redacted
