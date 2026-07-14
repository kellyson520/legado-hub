from dataclasses import replace
from uuid import uuid4

from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.source_review import SourceReviewItem, utcnow
from app.domain.repositories.source_review_repo import SourceReviewRepository


class SourceReviewService:
    def __init__(self, repo: SourceReviewRepository):
        self._repo = repo

    def enqueue_health_regression(
        self,
        *,
        source_version_id: str | None,
        source_url: str,
        decision: dict,
        created_by: str = 'system',
    ) -> SourceReviewItem:
        payload = {
            **decision,
            'source_url': source_url,
        }
        if source_version_id:
            payload['source_version_id'] = source_version_id
        item = SourceReviewItem(
            id=uuid4().hex,
            review_type='health_regression',
            source_version_id=source_version_id,
            source_url=source_url,
            summary=f"Health regression follow-up ({decision.get('action', 'review')})",
            payload=payload,
            status='candidate',
            created_by=created_by,
        )
        return self._repo.save_item(item)

    def enqueue_build_escalation(
        self,
        *,
        source_version_id: str | None,
        source_url: str,
        reason_tags: list[str],
        model_context: dict,
        created_by: str = 'system',
    ) -> SourceReviewItem:
        payload = {
            'candidate_url': source_url,
            'reason_tags': list(reason_tags),
            'model_context': dict(model_context),
        }
        if source_version_id:
            payload['source_version_id'] = source_version_id
        item = SourceReviewItem(
            id=uuid4().hex,
            review_type='build_escalation',
            source_version_id=source_version_id,
            source_url=source_url,
            summary='Manual source build review required',
            payload=payload,
            status='candidate',
            created_by=created_by,
        )
        return self._repo.save_item(item)

    def enqueue_audit_failure(
        self,
        *,
        source_version_id: str,
        source_url: str,
        audit_report: dict,
        created_by: str = 'system',
    ) -> SourceReviewItem:
        item_id = f'source-audit-failed:{source_version_id}'
        existing = self._repo.get_item(item_id)
        if existing is not None:
            return existing
        item = SourceReviewItem(
            id=item_id,
            review_type='source_audit_failed',
            source_version_id=source_version_id,
            source_url=source_url,
            summary='Source audit retry limit reached',
            payload={
                'candidate_url': source_url,
                'audit_report': dict(audit_report),
            },
            status='candidate',
            created_by=created_by,
        )
        return self._repo.save_item(item)

    def list_review_queue(self) -> list[SourceReviewItem]:
        return self._repo.list_items(status='candidate')

    def list_items(
        self,
        *,
        status: str | None = None,
        review_type: str | None = None,
    ) -> list[SourceReviewItem]:
        return self._repo.list_items(status=status, review_type=review_type)

    def resolve_review(
        self,
        item_id: str,
        *,
        reviewer_id: str,
        action: str,
    ) -> SourceReviewItem:
        if action not in {'resolve', 'dismiss'}:
            raise ValidationException('Only resolve and dismiss are supported')
        item = self._repo.get_item(item_id)
        if item is None:
            raise NotFoundException('Source review item not found')
        if item.status != 'candidate':
            raise ValidationException('Only candidate source review items can be resolved')

        resolved_at = utcnow()
        payload = dict(item.payload)
        payload['resolution'] = {
            'action': action,
            'reviewed_by': reviewer_id,
            'resolved_at': resolved_at.isoformat(),
        }
        resolved = replace(
            item,
            payload=payload,
            status='resolved',
            reviewed_by=reviewer_id,
            resolved_at=resolved_at,
        )
        return self._repo.save_item(resolved)
