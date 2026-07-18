import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.core.config import settings
from app.core.response import ok
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import AuditLogMiddleware, AuditRecord, RateLimitMiddleware, TraceMiddleware
from app.infrastructure.persistence.factory import (
    build_source_repository,
    build_source_runtime_service,
    close_interactive_browser_supervisor,
)
from app.infrastructure.legado.engine.runtime_process import RuntimeProcessManager
from app.interfaces.http.router import api_router
from app.tasks.scheduler import (
    run_event_delivery_job,
    run_source_build_job,
    start_scheduler,
    stop_scheduler,
)


logger = get_logger("lifespan")


def _persist_audit_record(record: AuditRecord) -> None:
    """Adapt the core middleware payload to the active domain repository."""
    from app.domain.entities.auth import AuditEvent
    from app.infrastructure.persistence.factory import build_auth_repository

    asyncio.run(
        build_auth_repository().record_audit(
            AuditEvent(
                actor_id=record.actor_id,
                action=record.action,
                resource=record.resource,
                detail=record.detail,
            )
        )
    )


async def _event_delivery_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await run_event_delivery_job(limit=settings.EVENT_DELIVERY_BATCH_SIZE)
        except Exception:
            # Keep the worker alive, but never hide a delivery failure from operators.
            logger.exception("event delivery worker iteration failed", extra={"action": "worker_error", "worker": "event_delivery"})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.EVENT_DELIVERY_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def _source_build_worker(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await run_source_build_job(limit=settings.SOURCE_BUILD_BATCH_SIZE)
        except Exception:
            logger.exception("source build worker iteration failed", extra={"action": "worker_error", "worker": "source_build"})
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
    scheduler_started = False
    app.state.runtime_process = RuntimeProcessManager()
    try:
        if settings.ENV != "test":
            app.state.runtime_process.health()
        await build_source_repository().delete_expired_ephemeral_book_sources()
        await build_source_runtime_service().register_published_book_sources()
        if settings.ENV != 'test':
            scheduler_job_ids = {'cleanup_ephemeral_sources'}
            if settings.SOURCE_HEALTH_PROBE_WORKER_ENABLED:
                scheduler_job_ids.add('probe_source_health')
            start_scheduler(job_ids=scheduler_job_ids)
            scheduler_started = True
        if settings.ENV != 'test' and settings.EVENT_DELIVERY_WORKER_ENABLED:
            stop_event = asyncio.Event()
            worker_task = asyncio.create_task(_event_delivery_worker(stop_event))
            app.state.event_delivery_worker_task = worker_task
        if settings.ENV != 'test' and settings.SOURCE_BUILD_WORKER_ENABLED:
            source_build_stop_event = asyncio.Event()
            source_build_worker_task = asyncio.create_task(_source_build_worker(source_build_stop_event))
            app.state.source_build_worker_task = source_build_worker_task
        yield
    finally:
        if scheduler_started:
            stop_scheduler()
        if stop_event is not None:
            stop_event.set()
        if source_build_stop_event is not None:
            source_build_stop_event.set()
        if worker_task is not None:
            await worker_task
        if source_build_worker_task is not None:
            await source_build_worker_task
        await asyncio.to_thread(close_interactive_browser_supervisor)
        app.state.runtime_process.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)
setup_logging(level=settings.LOG_LEVEL, enable_json=settings.LOG_JSON)
app.add_middleware(AuditLogMiddleware, audit_recorder=_persist_audit_record)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TraceMiddleware)
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return ok(
        data={"service": settings.APP_NAME, "version": settings.APP_VERSION},
        message="service ready",
        meta={},
    )


@app.get("/api/status")
def status(request: Request = None) -> dict:
    app_state = getattr(getattr(request, "app", None), "state", None)
    runtime_manager = getattr(app_state, "runtime_process", None)
    return ok(
        data={
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "env": settings.ENV,
            "runtime": runtime_manager.status() if runtime_manager is not None else {"state": "not_started"},
        },
        message="service ready",
        meta={},
    )
