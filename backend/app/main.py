import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.infrastructure.persistence.factory import (
    build_source_runtime_service,
    close_interactive_browser_supervisor,
)
from app.interfaces.http.router import api_router
from app.tasks.scheduler import run_event_delivery_job, run_source_build_job


async def _event_delivery_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await run_event_delivery_job(limit=settings.EVENT_DELIVERY_BATCH_SIZE)
        except Exception:
            # Keep the worker alive; failures are surfaced through delivery history.
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.EVENT_DELIVERY_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def _source_build_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await run_source_build_job(limit=settings.SOURCE_BUILD_BATCH_SIZE)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.SOURCE_BUILD_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = None
    stop_event = None
    source_build_worker_task = None
    source_build_stop_event = None
    await build_source_runtime_service().register_published_book_sources()
    if settings.ENV != 'test' and settings.EVENT_DELIVERY_WORKER_ENABLED:
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(_event_delivery_worker(stop_event))
        app.state.event_delivery_worker_task = worker_task
    if settings.ENV != 'test' and settings.SOURCE_BUILD_WORKER_ENABLED:
        source_build_stop_event = asyncio.Event()
        source_build_worker_task = asyncio.create_task(_source_build_worker(source_build_stop_event))
        app.state.source_build_worker_task = source_build_worker_task
    try:
        yield
    finally:
        if stop_event is not None:
            stop_event.set()
        if source_build_stop_event is not None:
            source_build_stop_event.set()
        if worker_task is not None:
            await worker_task
        if source_build_worker_task is not None:
            await source_build_worker_task
        await asyncio.to_thread(close_interactive_browser_supervisor)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {
        "success": True,
        "code": "OK",
        "message": "service ready",
        "data": {"service": settings.APP_NAME, "version": settings.APP_VERSION},
        "meta": {},
        "trace_id": None,
    }


@app.get("/api/status")
def status() -> dict:
    return {
        "success": True,
        "code": "OK",
        "message": "service ready",
        "data": {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "env": settings.ENV,
        },
        "meta": {},
        "trace_id": None,
    }
