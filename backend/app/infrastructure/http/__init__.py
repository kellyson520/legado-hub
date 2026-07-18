"""Shared outbound HTTP adapters.

Application services depend on the ports in ``app.application.ports.http``;
this package owns URL validation, DNS checks and concrete HTTP clients.
"""

from .outbound import SafeAsyncHttpClient, SafeSyncHttpClient, SafeWebhookSender

__all__ = ["SafeAsyncHttpClient", "SafeSyncHttpClient", "SafeWebhookSender"]

