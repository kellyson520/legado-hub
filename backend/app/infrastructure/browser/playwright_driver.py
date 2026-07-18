from __future__ import annotations

import asyncio
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from app.application.ports.browser import BrowserAttemptResult


class BrowserRuntimeUnavailable(RuntimeError):
    pass


@dataclass
class BrowserHandle:
    id: str
    profile_dir: Path
    initial_url: str
    allowed_origins: set[str]
    page: Any
    browser: Any
    playwright: Any
    processes: list[Any]
    relay_port: int


class PlaywrightBrowserDriver:
    """Run an ordinary local Chromium session without proxy or stealth features."""

    def __init__(
        self,
        *,
        chromium_path: str = 'chromium-browser',
        xvfb_path: str = 'Xvfb',
        x11vnc_path: str = 'x11vnc',
        websockify_path: str = 'websockify',
        which: Callable[[str], str | None] = shutil.which,
        process_runner: Callable[..., Any] = asyncio.create_subprocess_exec,
        connector: Callable[[str], Any] | None = None,
        port_factory: Callable[[], int] | None = None,
        display_number: int = 91,
    ):
        self._executables = {
            'chromium': chromium_path,
            'xvfb': xvfb_path,
            'x11vnc': x11vnc_path,
            'websockify': websockify_path,
        }
        self._which = which
        self._process_runner = process_runner
        self._connector = connector or self._connect_playwright
        self._port_factory = port_factory or self._find_loopback_port
        self._display_number = display_number

    async def start(self, *, profile_dir: Path, initial_url: str, allowed_origins: set[str]) -> BrowserHandle:
        runtime = self._require_runtime()
        profile_dir.mkdir(parents=True, exist_ok=False)
        display = f':{self._display_number}'
        cdp_port = self._port_factory()
        vnc_port = self._port_factory()
        relay_port = self._port_factory()
        processes: list[Any] = []
        playwright = browser = page = None
        try:
            processes.append(await self._process_runner(
                runtime['xvfb'], display, '-screen', '0', '1280x960x24', '-nolisten', 'tcp',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            ))
            processes.append(await self._process_runner(
                runtime['chromium'],
                '--no-first-run',
                '--no-default-browser-check',
                f'--user-data-dir={profile_dir}',
                '--remote-debugging-address=127.0.0.1',
                f'--remote-debugging-port={cdp_port}',
                initial_url,
                env={'DISPLAY': display},
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            ))
            playwright, browser, page = await self._connector(f'http://127.0.0.1:{cdp_port}')
            processes.append(await self._process_runner(
                runtime['x11vnc'], '-display', display, '-rfbport', str(vnc_port),
                '-localhost', '-nopw', '-forever', '-shared',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            ))
            processes.append(await self._process_runner(
                runtime['websockify'], f'127.0.0.1:{relay_port}', f'127.0.0.1:{vnc_port}',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            ))
            return BrowserHandle(
                id=profile_dir.name,
                profile_dir=profile_dir,
                initial_url=initial_url,
                allowed_origins=set(allowed_origins),
                page=page,
                browser=browser,
                playwright=playwright,
                processes=processes,
                relay_port=relay_port,
            )
        except Exception as exc:
            await self._close_resources(browser, playwright, processes, profile_dir)
            raise BrowserRuntimeUnavailable('browser_unavailable') from exc

    async def automatic_probe(self, handle: BrowserHandle) -> BrowserAttemptResult:
        response = await handle.page.goto(handle.initial_url, wait_until='domcontentloaded', timeout=15_000)
        current_origin = self._origin(str(getattr(handle.page, 'url', '') or handle.initial_url))
        if current_origin not in handle.allowed_origins:
            return BrowserAttemptResult.needs_manual('cross_origin_navigation')
        body = await handle.page.locator('body').inner_text(timeout=5_000)
        title = await handle.page.title()
        response_status = getattr(response, 'status', None)
        page_text = f'{title}\n{body}'.lower()
        if response_status in {401, 403, 429} or any(
            marker in page_text
            for marker in ('captcha', 'turnstile', 'just a moment', 'verify you are human', '加载中')
        ):
            return BrowserAttemptResult.needs_manual('verification_required')
        return BrowserAttemptResult.succeeded()

    async def close(self, handle: BrowserHandle) -> None:
        await self._close_resources(handle.browser, handle.playwright, handle.processes, handle.profile_dir)

    async def _close_resources(self, browser, playwright, processes: list[Any], profile_dir: Path) -> None:
        for resource, method_name in ((browser, 'close'), (playwright, 'stop')):
            method = getattr(resource, method_name, None)
            if callable(method):
                try:
                    result = method()
                    if hasattr(result, '__await__'):
                        await result
                except Exception:
                    pass
        for process in reversed(processes):
            try:
                if getattr(process, 'returncode', None) is None:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=3)
            except Exception:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
        shutil.rmtree(profile_dir, ignore_errors=True)

    def _require_runtime(self) -> dict[str, str]:
        runtime = {name: self._which(executable) for name, executable in self._executables.items()}
        missing = [name for name, executable in runtime.items() if not executable]
        if missing:
            raise BrowserRuntimeUnavailable('browser_unavailable')
        return {name: str(executable) for name, executable in runtime.items()}

    @staticmethod
    def _find_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            return int(listener.getsockname()[1])

    @staticmethod
    async def _connect_playwright(cdp_url: str) -> tuple[Any, Any, Any]:
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(cdp_url, timeout=15_000)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        return playwright, browser, page

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        return f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else ''
