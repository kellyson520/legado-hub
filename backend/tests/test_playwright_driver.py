import pytest


@pytest.mark.asyncio
async def test_playwright_driver_refuses_to_start_without_local_browser_runtime(tmp_path):
    from app.infrastructure.browser.playwright_driver import (
        BrowserRuntimeUnavailable,
        PlaywrightBrowserDriver,
    )

    driver = PlaywrightBrowserDriver(which=lambda _executable: None)

    with pytest.raises(BrowserRuntimeUnavailable, match='browser_unavailable'):
        await driver.start(
            profile_dir=tmp_path / 'profile',
            initial_url='https://books.example.test/',
            allowed_origins={'https://books.example.test'},
        )


@pytest.mark.asyncio
async def test_playwright_driver_starts_only_loopback_standard_browser_processes(tmp_path):
    from app.infrastructure.browser.playwright_driver import PlaywrightBrowserDriver

    calls = []

    class Process:
        returncode = None

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return 0

    async def process_runner(*argv, **kwargs):
        calls.append((argv, kwargs))
        return Process()

    class Page:
        url = 'https://books.example.test/'

    class Browser:
        async def close(self):
            return None

    class Playwright:
        async def stop(self):
            return None

    async def connector(cdp_url):
        assert cdp_url == 'http://127.0.0.1:43001'
        return Playwright(), Browser(), Page()

    ports = iter([43001, 43002, 43003])
    driver = PlaywrightBrowserDriver(
        which=lambda executable: f'/usr/bin/{executable}',
        process_runner=process_runner,
        connector=connector,
        port_factory=lambda: next(ports),
        display_number=91,
    )

    handle = await driver.start(
        profile_dir=tmp_path / 'profile',
        initial_url='https://books.example.test/',
        allowed_origins={'https://books.example.test'},
    )

    assert handle.relay_port == 43003
    assert calls[0][0] == ('/usr/bin/Xvfb', ':91', '-screen', '0', '1280x960x24', '-nolisten', 'tcp')
    chromium_args = calls[1][0]
    assert chromium_args[:2] == ('/usr/bin/chromium-browser', '--no-first-run')
    assert '--headless' not in chromium_args
    assert not any(argument.startswith('--proxy') for argument in chromium_args)
    assert '--remote-debugging-address=127.0.0.1' in chromium_args
    assert calls[2][0][:4] == ('/usr/bin/x11vnc', '-display', ':91', '-rfbport')
    assert calls[3][0] == ('/usr/bin/websockify', '127.0.0.1:43003', '127.0.0.1:43002')
