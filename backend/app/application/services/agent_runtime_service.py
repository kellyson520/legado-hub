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

    def record_request(
        self,
        *,
        run_id: str,
        tenant_id: str,
        owner_scope: str,
        book_id: int | None,
        chapter_id: int | None,
        entrypoint: str,
        conversation_id: str,
        provider: str,
        model: str,
        attempts: int,
        cache_hit: bool,
        usage: dict | None = None,
        cost: float = 0.0,
        tool_names: list[str] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> AgentRun:
        metadata = {
            "owner_scope": owner_scope,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "entrypoint": entrypoint,
            "conversation_id": conversation_id,
            "provider": provider,
            "model": model,
            "attempts": max(0, int(attempts or 0)),
            "cache_hit": bool(cache_hit),
            "usage": {
                "input_tokens": max(0, int((usage or {}).get("input_tokens", 0) or 0)),
                "output_tokens": max(0, int((usage or {}).get("output_tokens", 0) or 0)),
            },
            "cost": max(0.0, float(cost or 0.0)),
            "tool_names": [str(item)[:120] for item in (tool_names or [])[:50]],
            "evidence_ids": [str(item)[:120] for item in (evidence_ids or [])[:100]],
        }
        updater = getattr(self._repo, "update_request_metadata", None)
        if callable(updater):
            run = updater(run_id, tenant_id, metadata)
        else:
            run = self._repo.get_run(run_id, tenant_id)
        if run is None:
            raise LookupError("candidate agent run not found for tenant")
        self.history.append({"status": "request", "run_id": run_id, "tenant_id": tenant_id, **metadata})
        return run

    def record_rejected_tool(
        self,
        *,
        tenant_id: str,
        tool_name: str,
        arguments: dict | None = None,
        reason: str = "",
    ) -> None:
        safe_arguments = {
            key: value
            for key, value in (arguments or {}).items()
            if key in {"book_id", "chapter_id", "name", "query", "top_k", "limit", "owner_scope"}
            and not isinstance(value, (dict, list))
        }
        self.history.append(
            {
                "status": "rejected",
                "tenant_id": tenant_id,
                "tool_name": str(tool_name)[:120],
                "arguments": safe_arguments,
                "reason": str(reason)[:300],
            }
        )

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
