from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_engine_service,
    build_source_build_service,
    build_source_runtime_service,
)
from app.interfaces.http.deps import RequestIdentity, get_current_identity, require_permission


router = APIRouter()


class GenerateRequest(BaseModel):
    url: str
    source_type: str = "book"
    sample: dict | None = None


class EvaluateRequest(BaseModel):
    source: dict


class RuleTestRequest(BaseModel):
    rule: str
    sample: dict | str


class RepairRequest(BaseModel):
    source_version_id: str


class DeployRequest(BaseModel):
    source_version_id: str


class ReviewResolveRequest(BaseModel):
    action: str = "publish"


class SourceBuildConsoleRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    keyword: str = Field(default="", max_length=200)


@router.post("/generate")
async def generate(
    payload: GenerateRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_GENERATE)),
):
    service = build_source_runtime_service()
    data = await service.generate(payload.model_dump(), str(identity.user_id))
    return {"success": True, "code": "OK", "message": "engine generate scheduled", "data": data, "meta": {}, "trace_id": None}


@router.post("/evaluate")
async def evaluate(payload: EvaluateRequest, _=Depends(require_permission(Permission.ENGINE_EVALUATE))):
    service = build_engine_service()
    data = await service.evaluate(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine evaluation complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/repair")
async def repair(
    payload: RepairRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_REPAIR)),
):
    service = build_source_runtime_service()
    data = await service.repair(payload.source_version_id, str(identity.user_id))
    return {"success": True, "code": "OK", "message": "engine repair complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/test")
async def test_rule(payload: RuleTestRequest, _=Depends(require_permission(Permission.ENGINE_TEST))):
    service = build_engine_service()
    data = await service.test_rule(payload.model_dump())
    return {"success": True, "code": "OK", "message": "engine harness complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/regression")
async def regression(
    payload: DeployRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_REGRESSION)),
):
    service = build_source_runtime_service()
    data = await service.regression(payload.source_version_id, str(identity.user_id))
    return {"success": True, "code": "OK", "message": "engine regression complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/deploy")
async def deploy(
    payload: DeployRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_DEPLOY)),
):
    service = build_source_runtime_service()
    data = await service.deploy(payload.source_version_id, str(identity.user_id))
    return {"success": True, "code": "OK", "message": "engine deployment complete", "data": data, "meta": {}, "trace_id": None}


@router.post("/reviews/{source_version_id}/resolve")
async def resolve_review(
    source_version_id: str,
    payload: ReviewResolveRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_DEPLOY)),
):
    service = build_source_runtime_service()
    data = await service.resolve_review(
        source_version_id,
        reviewer_id=str(identity.user_id),
        action=payload.action,
    )
    return {"success": True, "code": "OK", "message": "engine review resolved", "data": data, "meta": {}, "trace_id": None}


@router.post("/source-builds")
async def submit_console_source_build(
    payload: SourceBuildConsoleRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_GENERATE)),
):
    submission = build_source_build_service().submit(
        tenant_id=f"console:{identity.user_id}",
        url=payload.url,
        keyword=payload.keyword,
        extra_job_payload={"trigger": "console_rule_lab"},
        idempotency_key_prefix="source.build.console",
    )
    return {
        "success": True,
        "code": "OK",
        "message": "engine source build accepted",
        "data": {
            "job_id": submission.job_id,
            "normalized_url": submission.normalized_url,
            "status": submission.status,
            "source_version_id": submission.source_version_id,
            "source_version_status": submission.source_version_status,
        },
        "meta": {},
        "trace_id": None,
    }


@router.get("/source-builds")
async def list_console_source_builds(_=Depends(require_permission(Permission.ENGINE_TEST))):
    data = await build_source_runtime_service().list_recent_versions(status="candidate", limit=50)
    return {
        "success": True,
        "code": "OK",
        "message": "engine source builds listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }


@router.get("/runs")
async def list_runs(_=Depends(require_permission(Permission.ENGINE_TEST))):
    service = build_source_runtime_service()
    data = await service.list_runs()
    return {"success": True, "code": "OK", "message": "engine runs listed", "data": data, "meta": {"total": len(data)}, "trace_id": None}


@router.get("/deployments")
async def list_deployments(_=Depends(require_permission(Permission.ENGINE_DEPLOY))):
    service = build_source_runtime_service()
    data = await service.list_deployments()
    return {
        "success": True,
        "code": "OK",
        "message": "engine deployments listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }
