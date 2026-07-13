from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.domain.entities.source_rule_version import SourceRuleVersion


@dataclass(frozen=True)
class SourceBuildSubmission:
    job_id: str
    normalized_url: str
    status: str = 'candidate'
    source_version_id: str = ''
    source_version_status: str = 'candidate'


class SourceBuildService:
    def __init__(self, job_service, source_runtime_repo):
        self._jobs = job_service
        self._runtime = source_runtime_repo

    def submit(
        self,
        *,
        tenant_id: str,
        url: str,
        keyword: str = '',
        extra_payload: dict | None = None,
        extra_job_payload: dict | None = None,
        idempotency_key_prefix: str = 'source.build',
    ) -> SourceBuildSubmission:
        normalized_url = self._normalize_url(url)
        rule_version = self._get_or_create_rule_version(
            tenant_id=tenant_id,
            normalized_url=normalized_url,
            keyword=keyword,
            extra_payload=extra_payload,
        )
        attempt = int(rule_version.payload.get('attempt', 1) or 1)
        job = self._jobs.enqueue(
            kind='source.build', tenant_id=tenant_id,
            payload={
                'url': normalized_url,
                'keyword': keyword,
                'source_version_id': rule_version.id,
                **(extra_job_payload or {}),
            },
            idempotency_key=f'{idempotency_key_prefix}:{normalized_url}:{keyword}:attempt-{attempt}',
        )
        return SourceBuildSubmission(
            job_id=job.id,
            normalized_url=normalized_url,
            status=rule_version.status,
            source_version_id=rule_version.id,
            source_version_status=rule_version.status,
        )

    def submit_discovery(
        self,
        *,
        tenant_id: str,
        url: str,
        baseline_source_version_id: str,
        reason: str,
        previous_status: str = 'published',
    ) -> SourceBuildSubmission:
        return self.submit(
            tenant_id=tenant_id,
            url=url,
            keyword='',
            extra_payload={
                'discovery': {
                    'trigger': 'health_regression',
                    'reason': reason,
                    'baseline_source_version_id': baseline_source_version_id,
                    'previous_status': previous_status,
                }
            },
            extra_job_payload={
                'trigger': 'health_regression',
                'reason': reason,
                'baseline_source_version_id': baseline_source_version_id,
                'previous_status': previous_status,
            },
            idempotency_key_prefix='source.build.discovery',
        )

    def submit_catalog_discovery(
        self,
        *,
        tenant_id: str,
        url: str,
        catalog_source_id: int | None = None,
        catalog_source_name: str = '',
        catalog_source_group: str = 'default',
    ) -> SourceBuildSubmission:
        return self.submit(
            tenant_id=tenant_id,
            url=url,
            keyword='',
            extra_payload={
                'discovery': {
                    'trigger': 'configured_catalog',
                    'catalog_source_id': catalog_source_id,
                    'catalog_source_name': catalog_source_name,
                    'catalog_source_group': catalog_source_group,
                }
            },
            extra_job_payload={
                'trigger': 'configured_catalog',
                'catalog_source_id': catalog_source_id,
                'catalog_source_name': catalog_source_name,
                'catalog_source_group': catalog_source_group,
            },
            idempotency_key_prefix='source.build.catalog',
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        parts = urlsplit(url.strip())
        if parts.scheme not in {'http', 'https'} or not parts.netloc:
            raise ValueError('url must be an absolute http(s) URL')
        path = parts.path.rstrip('/')
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ''))

    def _get_or_create_rule_version(
        self,
        *,
        tenant_id: str,
        normalized_url: str,
        keyword: str,
        extra_payload: dict | None = None,
    ) -> SourceRuleVersion:
        for version in self._runtime.list_versions('book', normalized_url):
            if (
                version.status == 'candidate'
                and version.created_by == tenant_id
                and version.payload.get('keyword', '') == keyword
            ):
                active = any(
                    job.payload.get('source_version_id') == version.id and job.status in {'queued', 'running'}
                    for job in self._jobs.list_jobs()
                )
                if active:
                    return SourceRuleVersion.from_source_version(version, canonical_url=normalized_url)

        version = self._runtime.create_candidate_version(
            source_type='book',
            source_id=normalized_url,
            payload={
                'canonical_url': normalized_url,
                'keyword': keyword,
                'submitted_by': tenant_id,
                'attempt': 1 + sum(
                    1 for version in self._runtime.list_versions('book', normalized_url)
                    if version.created_by == tenant_id and version.payload.get('keyword', '') == keyword
                ),
                'evidence': {
                    'search': {},
                    'work': {},
                    'toc': {},
                    'content': {},
                },
                **(extra_payload or {}),
            },
            created_by=tenant_id,
        )
        return SourceRuleVersion.from_source_version(version, canonical_url=normalized_url)
