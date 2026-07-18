import json

from sqlalchemy import or_

from app.core.pagination import LIKE_ESCAPE, like_pattern
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.agent_runtime import AgentRun, ToolEvidence, ToolInvocation, ToolResult
from app.domain.repositories.agent_runtime_repo import AgentRuntimeRepository

from .schema import AgentRunModel, ToolEvidenceModel, ToolInvocationModel, ToolResultModel


def _load_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


class SQLiteAgentRuntimeRepository(AgentRuntimeRepository):
    @staticmethod
    def _run_entity(model: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=model.id,
            tenant_id=model.tenant_id,
            agent_kind=model.agent_kind,
            input_payload=_load_dict(model.input_payload),
            status='candidate',
            created_at=model.created_at,
        )

    @staticmethod
    def _invocation_entity(model: ToolInvocationModel) -> ToolInvocation:
        return ToolInvocation(
            id=model.id,
            agent_run_id=model.agent_run_id,
            tenant_id=model.tenant_id,
            tool_name=model.tool_name,
            category=model.category,
            arguments=_load_dict(model.arguments),
            created_at=model.created_at,
        )

    @staticmethod
    def _result_entity(model: ToolResultModel) -> ToolResult:
        return ToolResult(
            id=model.id,
            tool_invocation_id=model.tool_invocation_id,
            tenant_id=model.tenant_id,
            status=model.status,
            data=_load_dict(model.data),
            error_code=model.error_code,
            created_at=model.created_at,
        )

    @staticmethod
    def _evidence_entity(model: ToolEvidenceModel) -> ToolEvidence:
        return ToolEvidence(
            id=model.id,
            tool_invocation_id=model.tool_invocation_id,
            tenant_id=model.tenant_id,
            evidence_type=model.evidence_type,
            resource_id=model.resource_id,
            payload=_load_dict(model.payload),
            created_at=model.created_at,
        )

    @staticmethod
    def _has_invocation(db, invocation_id: str, tenant_id: str) -> bool:
        return (
            db.query(ToolInvocationModel.id)
            .filter(ToolInvocationModel.id == invocation_id, ToolInvocationModel.tenant_id == tenant_id)
            .first()
            is not None
        )

    def create_run(self, run: AgentRun) -> AgentRun:
        db = SessionLocal()
        try:
            model = AgentRunModel(
                id=run.id,
                tenant_id=run.tenant_id,
                agent_kind=run.agent_kind,
                input_payload=json.dumps(run.input_payload, ensure_ascii=False),
                status='candidate',
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._run_entity(model)
        finally:
            db.close()

    def get_run(self, run_id: str, tenant_id: str) -> AgentRun | None:
        db = SessionLocal()
        try:
            model = (
                db.query(AgentRunModel)
                .filter(AgentRunModel.id == run_id, AgentRunModel.tenant_id == tenant_id)
                .first()
            )
            return self._run_entity(model) if model else None
        finally:
            db.close()

    def get_run_any_tenant(self, run_id: str) -> AgentRun | None:
        db = SessionLocal()
        try:
            model = db.query(AgentRunModel).filter(AgentRunModel.id == run_id).first()
            return self._run_entity(model) if model else None
        finally:
            db.close()

    def list_runs(self, *, tenant_id: str | None = None, limit: int = 50) -> list[AgentRun]:
        db = SessionLocal()
        try:
            query = db.query(AgentRunModel)
            if tenant_id is not None:
                query = query.filter(AgentRunModel.tenant_id == tenant_id)
            models = (
                query.order_by(AgentRunModel.created_at.desc(), AgentRunModel.id.desc())
                .limit(limit)
                .all()
            )
            return [self._run_entity(model) for model in models]
        finally:
            db.close()

    def list_runs_page(
        self,
        *,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[AgentRun], int]:
        db = SessionLocal()
        try:
            query = db.query(AgentRunModel)
            if tenant_id is not None:
                query = query.filter(AgentRunModel.tenant_id == tenant_id)
            if status:
                query = query.filter(AgentRunModel.status == status)
            normalized_search = search.strip()
            if normalized_search:
                pattern = like_pattern(normalized_search)
                query = query.filter(
                    or_(
                        AgentRunModel.id.ilike(pattern, escape=LIKE_ESCAPE),
                        AgentRunModel.agent_kind.ilike(pattern, escape=LIKE_ESCAPE),
                        AgentRunModel.tenant_id.ilike(pattern, escape=LIKE_ESCAPE),
                    )
                )
            total = query.count()
            models = (
                query.order_by(AgentRunModel.created_at.desc(), AgentRunModel.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return [self._run_entity(model) for model in models], total
        finally:
            db.close()

    def create_invocation(self, invocation: ToolInvocation) -> ToolInvocation:
        db = SessionLocal()
        try:
            run = (
                db.query(AgentRunModel.id)
                .filter(
                    AgentRunModel.id == invocation.agent_run_id,
                    AgentRunModel.tenant_id == invocation.tenant_id,
                    AgentRunModel.status == 'candidate',
                )
                .first()
            )
            if run is None:
                raise LookupError('candidate agent run not found for tenant')
            model = ToolInvocationModel(
                id=invocation.id,
                agent_run_id=invocation.agent_run_id,
                tenant_id=invocation.tenant_id,
                tool_name=invocation.tool_name,
                category=invocation.category,
                arguments=json.dumps(invocation.arguments, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._invocation_entity(model)
        finally:
            db.close()

    def create_result(self, result: ToolResult) -> ToolResult:
        db = SessionLocal()
        try:
            if not self._has_invocation(db, result.tool_invocation_id, result.tenant_id):
                raise LookupError('tool invocation not found for tenant')
            model = ToolResultModel(
                id=result.id,
                tool_invocation_id=result.tool_invocation_id,
                tenant_id=result.tenant_id,
                status=result.status,
                data=json.dumps(result.data, ensure_ascii=False),
                error_code=result.error_code,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._result_entity(model)
        finally:
            db.close()

    def create_evidence(self, evidence: ToolEvidence) -> ToolEvidence:
        db = SessionLocal()
        try:
            if not self._has_invocation(db, evidence.tool_invocation_id, evidence.tenant_id):
                raise LookupError('tool invocation not found for tenant')
            model = ToolEvidenceModel(
                id=evidence.id,
                tool_invocation_id=evidence.tool_invocation_id,
                tenant_id=evidence.tenant_id,
                evidence_type=evidence.evidence_type,
                resource_id=evidence.resource_id,
                payload=json.dumps(evidence.payload, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._evidence_entity(model)
        finally:
            db.close()

    def list_invocations(self, run_id: str, tenant_id: str) -> list[ToolInvocation] | None:
        db = SessionLocal()
        try:
            run = (
                db.query(AgentRunModel.id)
                .filter(AgentRunModel.id == run_id, AgentRunModel.tenant_id == tenant_id)
                .first()
            )
            if run is None:
                return None
            models = (
                db.query(ToolInvocationModel)
                .filter(ToolInvocationModel.agent_run_id == run_id, ToolInvocationModel.tenant_id == tenant_id)
                .order_by(ToolInvocationModel.created_at.asc(), ToolInvocationModel.id.asc())
                .all()
            )
            return [self._invocation_entity(model) for model in models]
        finally:
            db.close()

    def get_result(self, invocation_id: str, tenant_id: str) -> ToolResult | None:
        db = SessionLocal()
        try:
            model = (
                db.query(ToolResultModel)
                .filter(ToolResultModel.tool_invocation_id == invocation_id, ToolResultModel.tenant_id == tenant_id)
                .first()
            )
            return self._result_entity(model) if model else None
        finally:
            db.close()

    def list_evidence(self, invocation_id: str, tenant_id: str) -> list[ToolEvidence] | None:
        db = SessionLocal()
        try:
            if not self._has_invocation(db, invocation_id, tenant_id):
                return None
            models = (
                db.query(ToolEvidenceModel)
                .filter(ToolEvidenceModel.tool_invocation_id == invocation_id, ToolEvidenceModel.tenant_id == tenant_id)
                .order_by(ToolEvidenceModel.created_at.asc(), ToolEvidenceModel.id.asc())
                .all()
            )
            return [self._evidence_entity(model) for model in models]
        finally:
            db.close()
