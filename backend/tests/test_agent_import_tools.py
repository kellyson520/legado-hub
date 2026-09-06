import pytest

from app.application.services.agent_tool_registry import AgentToolRegistry
from app.core.exceptions import AuthorizationException


def test_import_and_source_diagnostic_tools_are_registered_for_correct_agents():
    registry = AgentToolRegistry()

    assert registry.get("novel.import_preview").allowed_agent_kinds == frozenset({"novel", "knowledge"})
    assert registry.get("novel.chapter_quality").allowed_agent_kinds == frozenset({"novel", "knowledge"})
    assert registry.get("source.build_status").allowed_agent_kinds == frozenset({"source_build"})
    assert registry.get("source.validation_report").allowed_agent_kinds == frozenset({"source_build"})


def test_diagnostic_tools_preserve_tenant_scope_enforcement():
    registry = AgentToolRegistry()

    with pytest.raises(AuthorizationException, match="cross-tenant"):
        registry.invoke(
            agent_kind="novel",
            tool_name="novel.import_preview",
            arguments={"tenant_id": "tenant-other"},
            tenant_id="tenant-owner",
        )


def test_unbound_diagnostic_tool_is_rejected_without_execution():
    registry = AgentToolRegistry()

    result = registry.invoke(
        agent_kind="source_build",
        tool_name="source.validation_report",
        arguments={},
        tenant_id="tenant-owner",
    )

    assert result.status == "rejected"
    assert result.error_code == "tool_not_implemented"
