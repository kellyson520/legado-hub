import json

from app.database import SessionLocal
from app.domain.entities.agent_runtime import AgentRun, ToolEvidence, ToolInvocation, ToolResult
from app.domain.repositories.agent_runtime_repo import AgentRuntimeRepository

from .schema import AgentRunModel, ToolEvidenceModel, ToolInvocationModel, ToolResultModel


def _load_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _load_list(raw: str | None) -> list:
    if not raw:
        return []
    value = json.loads(raw)
    return value if isinstance(value, list) else []


class SQLiteAgentRuntimeRepository(AgentRuntimeRepository):
    @staticmethod
    def _run_entity(model: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=model.id,
            tenant_id=model.tenant_id,
            agent_kind=model.agent_kind,
            input_payload=_load_dict(model.input_payload),
            request_metadata={
                "owner_scope": model.owner_scope,
                "book_id": model.book_id,
                "chapter_id": model.chapter_id,
                "entrypoint": model.entrypoint,
                "conversation_id": model.conversation_id,
                "provider": model.provider_name,
                "model": model.model_name,
                "attempts": model.attempt_count,
                "cache_hit": model.cache_hit,
                "usage": {
                    "input_tokens": model.input_tokens,
                    "output_tokens": model.output_tokens,
                },
                "cost": model.cost,
                "tool_names": _load_list(model.tool_names),
                "evidence_ids": _load_list(model.evidence_ids),
            },
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
                owner_scope=run.tenant_id,
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

    def update_request_metadata(self, run_id: str, tenant_id: str, metadata: dict) -> AgentRun:
        db = SessionLocal()
        try:
            model = (
                db.query(AgentRunModel)
                .filter(AgentRunModel.id == run_id, AgentRunModel.tenant_id == tenant_id)
                .first()
            )
            if model is None:
                raise LookupError('candidate agent run not found for tenant')
            usage = metadata.get('usage') if isinstance(metadata.get('usage'), dict) else {}
            model.owner_scope = str(metadata.get('owner_scope') or tenant_id)
            model.book_id = metadata.get('book_id')
            model.chapter_id = metadata.get('chapter_id')
            model.entrypoint = str(metadata.get('entrypoint') or '')
            model.conversation_id = str(metadata.get('conversation_id') or '')
            model.provider_name = str(metadata.get('provider') or '')
            model.model_name = str(metadata.get('model') or '')
            model.attempt_count = int(metadata.get('attempts') or 0)
            model.cache_hit = bool(metadata.get('cache_hit', False))
            model.input_tokens = int(usage.get('input_tokens') or 0)
            model.output_tokens = int(usage.get('output_tokens') or 0)
            model.cost = float(metadata.get('cost') or 0.0)
            model.tool_names = json.dumps(metadata.get('tool_names') or [], ensure_ascii=False)
            model.evidence_ids = json.dumps(metadata.get('evidence_ids') or [], ensure_ascii=False)
            db.commit()
            db.refresh(model)
            return self._run_entity(model)
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
