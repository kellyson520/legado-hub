import pytest


@pytest.mark.asyncio
async def test_rule_validate_awaits_an_async_validator_and_review_requires_full_validation():
    from app.application.services.source_build_tool_executor import (
        SourceBuildToolContext,
        SourceBuildToolExecutor,
    )

    reviewed: list[dict] = []

    async def validate_patch(patch):
        assert patch == {'searchUrl': 'https://books.example/search?q={{key}}'}
        return {
            'search': {'passed': True},
            'toc': {'passed': True},
            'content': {'passed': True},
        }

    executor = SourceBuildToolExecutor(SourceBuildToolContext(
        source_version_id='source-version-1',
        source_url='https://books.example/list',
        source_rule={},
        validate_patch=validate_patch,
        request_review=lambda arguments: reviewed.append(arguments) or {'requested': True},
    ))

    assert executor.handlers()['review.request']({'reason': 'needs review'}).error_code == 'full_validation_required'
    validation = await executor.handlers()['rule.validate']({
        'patch': {'searchUrl': 'https://books.example/search?q={{key}}'},
    })
    review = executor.handlers()['review.request']({'reason': 'validated'})

    assert validation.status == 'accepted'
    assert review.status == 'accepted'
    assert reviewed == [{'reason': 'validated'}]


def test_review_request_rejects_a_failed_full_chain_validation():
    from app.application.services.source_build_tool_executor import (
        SourceBuildToolContext,
        SourceBuildToolExecutor,
    )

    executor = SourceBuildToolExecutor(SourceBuildToolContext(
        source_version_id='source-version-1',
        source_url='https://books.example/list',
        source_rule={},
        validate_patch=lambda _patch: {
            'search': {'passed': True},
            'toc': {'passed': False},
            'content': {'passed': True},
        },
        request_review=lambda _arguments: {'requested': True},
    ))

    assert executor.handlers()['rule.validate']({'patch': {'searchUrl': 'https://books.example/search'}}).status == 'accepted'
    assert executor.handlers()['review.request']({}).error_code == 'full_validation_required'
