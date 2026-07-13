import pytest

from app.core.exceptions import AuthorizationException
from app.domain.entities.agent_runtime import AgentTool


@pytest.fixture
def registry():
    from app.application.services.agent_tool_registry import AgentToolRegistry

    return AgentToolRegistry()


def test_source_build_agent_cannot_call_unregistered_shell_tool(registry):
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='source_build',
            tool_name='shell.exec',
            arguments={},
            tenant_id='tenant-1',
        )


@pytest.mark.parametrize('tool_name', ('http.fetch', 'exec.command', 'postgres.query'))
def test_public_registration_cannot_extend_the_agent_tool_allowlist(registry, tool_name):
    tool = AgentTool(tool_name, 'operate', frozenset({'source_build'}), lambda _: pytest.fail('handler ran'))

    with pytest.raises((AuthorizationException, AttributeError)):
        registry.register(tool)


def test_review_agent_cannot_resolve_reviews(registry):
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='review',
            tool_name='review.resolve',
            arguments={},
            tenant_id='tenant-1',
        )


def test_tool_invocation_requires_tenant_id(registry):
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='knowledge',
            tool_name='knowledge.propose',
            arguments={'entity': {'name': 'Lin'}, 'evidence': ['chapter-1']},
        )


@pytest.mark.parametrize('tenant_key', ('tenant_id', 'tenantId', 'tenantID', 'tenant', 'tenant_ids', 'tenantIds'))
def test_tool_invocation_rejects_cross_tenant_values_at_any_nesting_level(registry, tenant_key):
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='knowledge',
            tool_name='knowledge.propose',
            arguments={
                'entity': {'name': 'Lin', 'scope': {tenant_key: 'other'}},
                'evidence': ['chapter-1'],
            },
            tenant_id='tenant-1',
        )


def test_knowledge_agent_cannot_inspect_a_source(registry):
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='knowledge',
            tool_name='source.inspect',
            arguments={'url': 'https://example.test/books'},
            tenant_id='tenant-1',
        )


def test_knowledge_proposal_requires_evidence(registry):
    result = registry.invoke(
        agent_kind='knowledge',
        tool_name='knowledge.propose',
        arguments={'entity': {'name': 'Lin'}},
        tenant_id='tenant-1',
    )

    assert result.status == 'rejected'
    assert result.error_code == 'evidence_required'


def test_source_build_agent_gets_a_rejected_result_for_unimplemented_source_inspection(registry):
    result = registry.invoke(
        agent_kind='source_build',
        tool_name='source.inspect',
        arguments={'url': 'https://example.test/books'},
        tenant_id='tenant-1',
    )

    assert result.status == 'rejected'
    assert result.error_code == 'tool_not_implemented'


def test_source_inspect_handler_is_invoked_and_cross_tenant_arguments_are_rejected():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.domain.entities.agent_runtime import ToolResult

    registry = AgentToolRegistry(
        source_build_handlers={
            'source.inspect': lambda arguments: ToolResult(
                status='accepted', data={'source_version_id': arguments['source_version_id']},
            )
        }
    )
    accepted = registry.invoke(
        agent_kind='source_build',
        tool_name='source.inspect',
        arguments={'source_version_id': 'sv-1'},
        tenant_id='tenant-1',
    )

    assert accepted.status == 'accepted'
    assert accepted.data['source_version_id'] == 'sv-1'
    with pytest.raises(AuthorizationException):
        registry.invoke(
            agent_kind='source_build',
            tool_name='source.inspect',
            arguments={'tenant_id': 'tenant-2'},
            tenant_id='tenant-1',
        )


def test_knowledge_proposal_with_evidence_is_accepted(registry):
    result = registry.invoke(
        agent_kind='knowledge',
        tool_name='knowledge.propose',
        arguments={'entity': {'name': 'Lin'}, 'evidence': ['chapter-1']},
        tenant_id='tenant-1',
    )

    assert result.status == 'accepted'
