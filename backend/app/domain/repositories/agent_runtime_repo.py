from abc import ABC, abstractmethod

from app.domain.entities.agent_runtime import AgentRun, ToolEvidence, ToolInvocation, ToolResult


class AgentRuntimeRepository(ABC):
    @abstractmethod
    def create_run(self, run: AgentRun) -> AgentRun:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str, tenant_id: str) -> AgentRun | None:
        raise NotImplementedError

    @abstractmethod
    def get_run_any_tenant(self, run_id: str) -> AgentRun | None:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self, *, tenant_id: str | None = None, limit: int = 50) -> list[AgentRun]:
        raise NotImplementedError

    @abstractmethod
    def create_invocation(self, invocation: ToolInvocation) -> ToolInvocation:
        raise NotImplementedError

    @abstractmethod
    def create_result(self, result: ToolResult) -> ToolResult:
        raise NotImplementedError

    @abstractmethod
    def create_evidence(self, evidence: ToolEvidence) -> ToolEvidence:
        raise NotImplementedError

    @abstractmethod
    def list_invocations(self, run_id: str, tenant_id: str) -> list[ToolInvocation] | None:
        raise NotImplementedError

    @abstractmethod
    def get_result(self, invocation_id: str, tenant_id: str) -> ToolResult | None:
        raise NotImplementedError

    @abstractmethod
    def list_evidence(self, invocation_id: str, tenant_id: str) -> list[ToolEvidence] | None:
        raise NotImplementedError
