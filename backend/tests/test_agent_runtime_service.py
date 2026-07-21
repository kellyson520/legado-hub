def test_agent_runtime_persists_candidate_run_tool_results_and_evidence_by_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runtime.sqlite3'))

    from app.infrastructure.persistence.factory import build_agent_runtime_service

    service = build_agent_runtime_service()
    run = service.create_run(
        tenant_id='tenant-1',
        agent_kind='knowledge',
        input_payload={'work_id': 'work-1'},
    )
    invocation = service.record_tool_invocation(
        run_id=run.id,
        tenant_id='tenant-1',
        tool_name='knowledge.propose',
        category='propose',
        arguments={'entity': {'name': 'Lin'}, 'evidence': ['chapter-1']},
    )
    result = service.record_tool_result(
        invocation_id=invocation.id,
        tenant_id='tenant-1',
        status='accepted',
        data={'proposal_id': 'candidate-1'},
    )
    evidence = service.record_tool_evidence(
        invocation_id=invocation.id,
        tenant_id='tenant-1',
        evidence_type='chapter_excerpt',
        resource_id='chapter-1',
        payload={'quote': 'Lin trusts Mei'},
    )

    stored = service.get_run(run.id, tenant_id='tenant-1')
    history = service.get_tool_history(run.id, tenant_id='tenant-1')

    assert run.status == 'candidate'
    assert stored is not None
    assert stored.input_payload == {'work_id': 'work-1'}
    assert history is not None
    assert history[0].id == invocation.id
    assert history[0].result == result
    assert history[0].evidence == [evidence]
    assert result.data == {'proposal_id': 'candidate-1'}
    assert evidence.resource_id == 'chapter-1'
    assert service.get_run(run.id, tenant_id='tenant-2') is None
    assert service.get_tool_history(run.id, tenant_id='tenant-2') is None


def test_agent_runtime_lists_recent_runs_for_admin_queries(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runtime-list.sqlite3'))

    from app.infrastructure.persistence.factory import build_agent_runtime_service

    service = build_agent_runtime_service()
    older = service.create_run(
        tenant_id='tenant-1',
        agent_kind='knowledge',
        input_payload={'work_id': 'work-1'},
    )
    newer = service.create_run(
        tenant_id='tenant-2',
        agent_kind='source_build',
        input_payload={'url': 'https://example.test/books'},
    )

    runs = service.list_runs(limit=10)

    assert [item.id for item in runs[:2]] == [newer.id, older.id]
    assert service.get_run_admin(newer.id) is not None


def test_agent_runtime_keeps_a_local_audit_trace_for_application_services(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runtime-history.sqlite3'))

    from app.infrastructure.persistence.factory import build_agent_runtime_service

    service = build_agent_runtime_service()
    run = service.create_run(tenant_id='user:1', agent_kind='novel', input_payload={'book_id': 7})
    invocation = service.record_tool_invocation(
        run_id=run.id,
        tenant_id='user:1',
        tool_name='reading.progress',
        category='read',
        arguments={'book_id': 7},
    )
    service.record_tool_result(
        invocation_id=invocation.id,
        tenant_id='user:1',
        status='accepted',
        data={'percent': 0.42},
    )

    assert service.history[-1]['status'] == 'accepted'
    assert service.history[-1]['tool_name'] == 'reading.progress'


def test_agent_runtime_persists_novel_request_usage_without_content_payload(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'agent-runtime-request.sqlite3'))

    from app.infrastructure.persistence.factory import build_agent_runtime_service

    service = build_agent_runtime_service()
    run = service.create_run(
        tenant_id='user:1',
        agent_kind='novel',
        input_payload={'book_id': 7, 'entrypoint': 'reader'},
    )
    service.record_request(
        run_id=run.id,
        tenant_id='user:1',
        owner_scope='user:1',
        book_id=7,
        chapter_id=2,
        entrypoint='reader',
        conversation_id='conversation-1',
        provider='deepseek',
        model='deepseek-chat',
        attempts=2,
        cache_hit=False,
        usage={'input_tokens': 12, 'output_tokens': 8},
        cost=0.03,
        tool_names=['chapter.search'],
        evidence_ids=['chapter:2'],
    )

    stored = service.get_run(run.id, tenant_id='user:1')

    assert stored is not None
    assert stored.request_metadata == {
        'owner_scope': 'user:1',
        'book_id': 7,
        'chapter_id': 2,
        'entrypoint': 'reader',
        'conversation_id': 'conversation-1',
        'provider': 'deepseek',
        'model': 'deepseek-chat',
        'attempts': 2,
        'cache_hit': False,
        'usage': {'input_tokens': 12, 'output_tokens': 8},
        'cost': 0.03,
        'tool_names': ['chapter.search'],
        'evidence_ids': ['chapter:2'],
    }
