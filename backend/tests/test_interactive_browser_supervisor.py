import asyncio
import threading

import pytest


@pytest.mark.asyncio
async def test_supervisor_keeps_browser_session_on_one_owner_loop_across_worker_and_http_loops(tmp_path):
    from app.application.services.interactive_browser_service import (
        BrowserValidationResult,
        InteractiveBrowserService,
    )
    from tests.test_interactive_browser_service import (
        EnabledSettings,
        FakeSessionRepository,
        RecordingDriver,
    )

    from app.application.services.interactive_browser_supervisor import InteractiveBrowserSupervisor

    expiry_started = threading.Event()
    release_expiry = threading.Event()
    operations = []

    class LoopRecordingDriver(RecordingDriver):
        async def start(self, **kwargs):
            operations.append(('start', threading.get_ident(), id(asyncio.get_running_loop())))
            return await super().start(**kwargs)

        async def automatic_probe(self, handle):
            operations.append(('automatic_probe', threading.get_ident(), id(asyncio.get_running_loop())))
            return await super().automatic_probe(handle)

        async def close(self, handle):
            operations.append(('close', threading.get_ident(), id(asyncio.get_running_loop())))
            return await super().close(handle)

    async def expiry_sleep(_delay):
        expiry_started.set()
        await asyncio.to_thread(release_expiry.wait)

    async def probe_runner(_handle, _source_rule, _keyword):
        operations.append(('full_chain_probe', threading.get_ident(), id(asyncio.get_running_loop())))
        return BrowserValidationResult.passed({
            'search': {'status': 'ok', 'hit_count': 1},
            'toc': {'status': 'ok', 'hit_count': 1},
            'content': {'status': 'ok', 'content_length': 120},
        })

    repo = FakeSessionRepository()
    driver = LoopRecordingDriver()
    supervisor = InteractiveBrowserSupervisor(lambda: InteractiveBrowserService(
        repo=repo,
        driver=driver,
        settings=EnabledSettings(),
        profile_root=tmp_path,
        probe_runner=probe_runner,
        expiry_sleep=expiry_sleep,
    ))
    worker_loop_ids = []
    created = []

    def source_scheduler_worker():
        async def create_manual_session():
            worker_loop_ids.append(id(asyncio.get_running_loop()))
            return await supervisor.start_or_resume(
                source_version_id='source-version-1',
                owner_id='42',
                target_url='https://books.example.test/book/1',
            )

        created.append(asyncio.run(create_manual_session()))

    worker = threading.Thread(target=source_scheduler_worker)
    worker.start()
    worker.join(timeout=3)

    try:
        assert worker.is_alive() is False
        session = created[0]
        assert expiry_started.wait(timeout=1)

        validation = await supervisor.continue_validation(
            session.id,
            owner_id='42',
            source_rule={'id': 17, 'bookSourceUrl': 'https://books.example.test/book/1'},
            keyword='sample',
        )

        assert validation.passed is True
        assert worker_loop_ids[0] != supervisor.owner_loop_id
        assert {thread_id for _name, thread_id, _loop_id in operations} == {supervisor.owner_thread_id}
        assert {loop_id for _name, _thread_id, loop_id in operations} == {supervisor.owner_loop_id}
        assert [name for name, _thread_id, _loop_id in operations] == [
            'start', 'automatic_probe', 'full_chain_probe', 'close',
        ]
    finally:
        release_expiry.set()
        supervisor.close()
