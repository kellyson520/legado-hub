from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, Callable


class InteractiveBrowserSupervisor:
    """Owns browser resources on one dedicated asyncio loop for this process."""

    def __init__(self, service_factory: Callable[[], Any]):
        self._service_factory = service_factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._service: Any = None
        self._error: BaseException | None = None
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name='interactive-browser-supervisor',
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError('interactive_browser_supervisor_start_timeout')
        if self._error is not None:
            raise RuntimeError('interactive_browser_supervisor_start_failed') from self._error

    @property
    def owner_thread_id(self) -> int:
        return self._thread.ident or 0

    @property
    def owner_loop_id(self) -> int:
        return id(self._loop)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._service = self._service_factory()
        except BaseException as exc:
            self._error = exc
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._shutdown_service())
            finally:
                loop.close()

    async def _shutdown_service(self) -> None:
        if self._service is None:
            return
        close = getattr(self._service, 'aclose', None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
            return
        close_handle = getattr(self._service, '_close_handle', None)
        handles = getattr(self._service, '_handles', {})
        if callable(close_handle):
            for session_id in list(handles):
                await close_handle(session_id)
        for task in list(getattr(self._service, '_expiry_tasks', {}).values()):
            task.cancel()
        pending = list(getattr(self._service, '_expiry_tasks', {}).values())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _invoke(self, method: str, *args, **kwargs):
        value = getattr(self._service, method)(*args, **kwargs)
        return await value if inspect.isawaitable(value) else value

    async def _submit(self, method: str, *args, **kwargs):
        if self._closed or self._loop is None:
            raise RuntimeError('interactive_browser_supervisor_closed')
        future = asyncio.run_coroutine_threadsafe(self._invoke(method, *args, **kwargs), self._loop)
        return await asyncio.wrap_future(future)

    async def start_or_resume(self, **kwargs):
        return await self._submit('start_or_resume', **kwargs)

    async def attempt_automatic(self, **kwargs):
        return await self._submit('attempt_automatic', **kwargs)

    async def get_for_owner(self, session_id: str, *, owner_id: str):
        return await self._submit('get_for_owner', session_id, owner_id=owner_id)

    async def cancel(self, session_id: str, *, owner_id: str):
        return await self._submit('cancel', session_id, owner_id=owner_id)

    async def issue_relay_ticket(self, session_id: str, *, owner_id: str):
        return await self._submit('issue_relay_ticket', session_id, owner_id=owner_id)

    async def consume_relay_ticket(self, token: str, *, owner_id: str):
        return await self._submit('consume_relay_ticket', token, owner_id=owner_id)

    async def continue_validation(self, session_id: str, **kwargs):
        return await self._submit('continue_validation', session_id, **kwargs)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        self._thread.join(timeout=5)
