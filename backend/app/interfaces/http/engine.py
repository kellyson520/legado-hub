import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.core.response import from_paginated_result, ok
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


class RegexTestRequest(BaseModel):
    text: str
    pattern: str
    replacement: str | None = None


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
    return ok(data=data, message="engine generate scheduled", meta={})


@router.post("/evaluate")
async def evaluate(payload: EvaluateRequest, _=Depends(require_permission(Permission.ENGINE_EVALUATE))):
    service = build_engine_service()
    data = await service.evaluate(payload.model_dump())
    return ok(data=data, message="engine evaluation complete", meta={})


@router.post("/repair")
async def repair(
    payload: RepairRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_REPAIR)),
):
    service = build_source_runtime_service()
    data = await service.repair(payload.source_version_id, str(identity.user_id))
    return ok(data=data, message="engine repair complete", meta={})


@router.post("/test")
async def test_rule(payload: RuleTestRequest, _=Depends(require_permission(Permission.ENGINE_TEST))):
    service = build_engine_service()
    data = await service.test_rule(payload.model_dump())
    return ok(data=data, message="engine harness complete", meta={})


@router.post("/regex-test")
async def regex_test(payload: RegexTestRequest, _=Depends(require_permission(Permission.ENGINE_TEST))):
    try:
        compiled = re.compile(payload.pattern)
        matches = [
            {"match": match.group(0), "groups": list(match.groups()), "span": list(match.span())}
            for match in compiled.finditer(payload.text)
        ]
        replacement_preview = None
        if payload.replacement is not None:
            replacement = re.sub(r"\$\{(\d+)\}|\$(\d+)", lambda match: f"\\g<{match.group(1) or match.group(2)}>", payload.replacement)
            replacement_preview = compiled.sub(replacement, payload.text)
        data = {"match_count": len(matches), "matches": matches, "replacement_preview": replacement_preview, "error": None}
    except re.error as exc:
        data = {"match_count": 0, "matches": [], "replacement_preview": None, "error": str(exc)}
    return ok(data=data, message="正则测试完成", meta={})


@router.post("/regression")
async def regression(
    payload: DeployRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_REGRESSION)),
):
    service = build_source_runtime_service()
    data = await service.regression(payload.source_version_id, str(identity.user_id))
    return ok(data=data, message="engine regression complete", meta={})


@router.post("/deploy")
async def deploy(
    payload: DeployRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_DEPLOY)),
):
    service = build_source_runtime_service()
    data = await service.deploy(payload.source_version_id, str(identity.user_id))
    return ok(data=data, message="engine deployment complete", meta={})


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
    return ok(data=data, message="engine review resolved", meta={})


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
    return ok(
        data={
            "job_id": submission.job_id,
            "normalized_url": submission.normalized_url,
            "status": submission.status,
            "source_version_id": submission.source_version_id,
            "source_version_status": submission.source_version_status,
        },
        message="engine source build accepted",
        meta={},
    )


@router.get("/source-builds")
async def list_console_source_builds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    result = await build_source_runtime_service().list_recent_versions_page(
        status="candidate", page=page, page_size=page_size, search=search
    )
    return from_paginated_result(result, message="engine source builds listed")


@router.get("/runs")
async def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    service = build_source_runtime_service()
    result = await service.list_runs_page(page=page, page_size=page_size, search=search)
    return from_paginated_result(result, message="engine runs listed")


@router.get("/deployments")
async def list_deployments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.ENGINE_DEPLOY)),
):
    service = build_source_runtime_service()
    result = await service.list_deployments_page(page=page, page_size=page_size, search=search, status=status)
    return from_paginated_result(result, message="engine deployments listed")
