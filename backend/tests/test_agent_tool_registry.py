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


@pytest.mark.asyncio
async def test_ainvoke_runs_async_handlers_but_invoke_rejects_them_without_running():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.domain.entities.agent_runtime import ToolResult

    calls = []

    async def inspect_page(arguments):
        calls.append(arguments)
        return ToolResult(status='accepted', data={'url': arguments['url']})

    registry = AgentToolRegistry(source_build_handlers={'page.inspect': inspect_page})

    synchronous_result = registry.invoke(
        agent_kind='source_build',
        tool_name='page.inspect',
        arguments={'url': 'https://books.example/list'},
        tenant_id='tenant-1',
    )
    asynchronous_result = await registry.ainvoke(
        agent_kind='source_build',
        tool_name='page.inspect',
        arguments={'url': 'https://books.example/list'},
        tenant_id='tenant-1',
    )

    assert synchronous_result.error_code == 'async_tool_requires_ainvoke'
    assert calls == [{'url': 'https://books.example/list'}]
    assert asynchronous_result.status == 'accepted'


@pytest.mark.asyncio
async def test_ainvoke_preserves_tenant_checks_and_fixed_page_tool_allowlist():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.domain.entities.agent_runtime import ToolResult

    registry = AgentToolRegistry(source_build_handlers={
        'page.inspect': lambda _arguments: ToolResult(status='accepted'),
        'page.request': lambda _arguments: ToolResult(status='accepted'),
        'shell.exec': lambda _arguments: ToolResult(status='accepted'),
    })

    assert registry.get('page.inspect').handler is not None
    assert registry.get('page.request').handler is not None
    with pytest.raises(AuthorizationException):
        await registry.ainvoke(
            agent_kind='source_build',
            tool_name='page.inspect',
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


def test_registry_exposes_bounded_novel_tools_for_the_novel_agent(registry):
    chapter_search = registry.get('chapter.search')
    reading_progress = registry.get('reading.progress')

    assert chapter_search is not None
    assert chapter_search.category == 'read'
    assert 'novel' in chapter_search.allowed_agent_kinds
    assert reading_progress is not None
