from uuid import uuid4

from app.domain.entities.agent_runtime import AgentRun, ToolEvidence, ToolInvocation, ToolResult


class AgentRuntimeService:
    """Persists an auditable, tenant-isolated candidate-only agent trace."""

    _TOOL_CATEGORIES = frozenset({'read', 'propose', 'operate'})
    _RESULT_STATUSES = frozenset({'accepted', 'rejected'})

    def __init__(self, repo):
        self._repo = repo
        # A bounded in-process trace is useful to application services and
        # tests while the durable repository remains the source of truth.
        self.history: list[dict] = []
        self._invocation_names: dict[str, str] = {}

    def create_run(self, *, tenant_id: str, agent_kind: str, input_payload: dict | None = None) -> AgentRun:
        run = self._repo.create_run(
            AgentRun(
                id=uuid4().hex,
                tenant_id=tenant_id,
                agent_kind=agent_kind,
                input_payload=input_payload or {},
            )
        )
        self.history.append({
            'status': 'started',
            'run_id': run.id,
            'tenant_id': tenant_id,
            'agent_kind': agent_kind,
        })
        return run

    def get_run(self, run_id: str, *, tenant_id: str) -> AgentRun | None:
        return self._repo.get_run(run_id, tenant_id)

    def get_run_admin(self, run_id: str) -> AgentRun | None:
        return self._repo.get_run_any_tenant(run_id)

    def list_runs(self, *, tenant_id: str | None = None, limit: int = 50) -> list[AgentRun]:
        return self._repo.list_runs(tenant_id=tenant_id, limit=limit)

    def record_tool_invocation(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        category: str,
        arguments: dict | None = None,
    ) -> ToolInvocation:
        if category not in self._TOOL_CATEGORIES:
            raise ValueError(f'unsupported tool category: {category}')
        invocation = self._repo.create_invocation(
            ToolInvocation(
                id=uuid4().hex,
                agent_run_id=run_id,
                tenant_id=tenant_id,
                tool_name=tool_name,
                category=category,
                arguments=arguments or {},
            )
        )
        self._invocation_names[invocation.id] = tool_name
        self.history.append({
            'status': 'invoked',
            'invocation_id': invocation.id,
            'tenant_id': tenant_id,
            'tool_name': tool_name,
            'category': category,
        })
        return invocation

    def record_tool_result(
        self,
        *,
        invocation_id: str,
        tenant_id: str,
        status: str,
        data: dict | None = None,
        error_code: str | None = None,
    ) -> ToolResult:
        if status not in self._RESULT_STATUSES:
            raise ValueError(f'unsupported tool result status: {status}')
        result = self._repo.create_result(
            ToolResult(
                id=uuid4().hex,
                tool_invocation_id=invocation_id,
                tenant_id=tenant_id,
                status=status,
                data=data or {},
                error_code=error_code,
            )
        )
        self.history.append({
            'status': status,
            'invocation_id': invocation_id,
            'tenant_id': tenant_id,
            'tool_name': self._invocation_names.get(invocation_id, ''),
            'error_code': error_code,
        })
        return result

    def record_tool_evidence(
        self,
        *,
        invocation_id: str,
        tenant_id: str,
        evidence_type: str,
        resource_id: str,
        payload: dict | None = None,
    ) -> ToolEvidence:
        evidence = self._repo.create_evidence(
            ToolEvidence(
                id=uuid4().hex,
                tool_invocation_id=invocation_id,
                tenant_id=tenant_id,
                evidence_type=evidence_type,
                resource_id=resource_id,
                payload=payload or {},
            )
        )
        self.history.append({
            'status': 'evidence',
            'invocation_id': invocation_id,
            'tenant_id': tenant_id,
            'evidence_type': evidence_type,
            'resource_id': resource_id,
        })
        return evidence

    def get_tool_history(self, run_id: str, *, tenant_id: str) -> list[ToolInvocation] | None:
        invocations = self._repo.list_invocations(run_id, tenant_id)
        if invocations is None:
            return None
        for invocation in invocations:
            invocation.result = self._repo.get_result(invocation.id, tenant_id)
            invocation.evidence = self._repo.list_evidence(invocation.id, tenant_id) or []
        return invocations
