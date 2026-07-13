from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_engine_service, build_source_runtime_service
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
