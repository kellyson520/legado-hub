from fastapi import APIRouter

from app.interfaces.http import (
    admin,
    agent_runs,
    ai,
    auth,
    client_access,
    client_reading,
    dashboard,
    engine,
    events,
    export,
    health,
    interactive_browser,
    jobs,
    novel,
    novel_analysis,
    reading,
    source_build,
    source_health,
    sources,
    system,
    translation,
    work_knowledge,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(client_access.router, tags=['client-access'])
api_router.include_router(client_reading.router, prefix="/client", tags=['client-reading'])
api_router.include_router(jobs.router, tags=['jobs'])
api_router.include_router(agent_runs.router, tags=['agent-runs'])
api_router.include_router(source_build.router, tags=['source-builds'])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(engine.router, prefix="/engine", tags=["engine"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(translation.router, prefix="/translation", tags=["translation"])
api_router.include_router(novel.router, prefix="/novel", tags=["novel"])
api_router.include_router(novel_analysis.router, prefix="/novel-analysis", tags=["novel-analysis"])
api_router.include_router(work_knowledge.router, prefix="/work-knowledge", tags=["work-knowledge"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(reading.router, prefix="/reading", tags=["reading"])
api_router.include_router(source_health.router, prefix="/source-health", tags=["source-health"])
api_router.include_router(interactive_browser.router, prefix='/interactive-browser', tags=['interactive-browser'])
