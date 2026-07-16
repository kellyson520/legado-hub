from math import ceil
from uuid import uuid4

from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.work_knowledge import WorkKnowledgeProposal


class WorkKnowledgeService:
    def __init__(self, repo):
        self._repo = repo

    def _create_proposal(
        self,
        *,
        work_id: str,
        source_chapter_id: str,
        proposal_type: str,
        evidence: str,
        payload: dict,
        actor_id: str,
        subject: str = '',
        relation: str = '',
        object_name: str = '',
    ) -> WorkKnowledgeProposal:
        proposal = WorkKnowledgeProposal(
            id=uuid4().hex,
            work_id=work_id,
            source_chapter_id=source_chapter_id,
            proposal_type=proposal_type,
            subject=subject,
            relation=relation,
            object_name=object_name,
            evidence=evidence,
            payload=payload,
            status='candidate',
            created_by=actor_id,
        )
        return self._repo.save_proposal(proposal)

    def propose_relation(
        self,
        *,
        work_id: str,
        source_chapter_id: str,
        evidence: str,
        relation: str,
        actor_id: str = 'agent',
    ) -> WorkKnowledgeProposal:
        subject, object_name = self._infer_subject_object(evidence, relation)
        return self._create_proposal(
            work_id=work_id,
            source_chapter_id=source_chapter_id,
            evidence=evidence,
            proposal_type='character_relation',
            payload={
                'subject': subject,
                'relation': relation,
                'object_name': object_name,
                'evidence': evidence,
            },
            actor_id=actor_id,
            subject=subject,
            relation=relation,
            object_name=object_name,
        )

    def propose_plot_event(
        self,
        *,
        work_id: str,
        source_chapter_id: str,
        evidence: str,
        event_title: str,
        summary: str,
        actor_id: str = 'agent',
    ) -> WorkKnowledgeProposal:
        return self._create_proposal(
            work_id=work_id,
            source_chapter_id=source_chapter_id,
            proposal_type='plot_event',
            evidence=evidence,
            payload={
                'event_title': event_title,
                'summary': summary,
                'evidence': evidence,
            },
            actor_id=actor_id,
        )

    def propose_world_rule(
        self,
        *,
        work_id: str,
        source_chapter_id: str,
        evidence: str,
        rule_name: str,
        description: str,
        actor_id: str = 'agent',
    ) -> WorkKnowledgeProposal:
        return self._create_proposal(
            work_id=work_id,
            source_chapter_id=source_chapter_id,
            proposal_type='world_rule',
            evidence=evidence,
            payload={
                'rule_name': rule_name,
                'description': description,
                'evidence': evidence,
            },
            actor_id=actor_id,
        )

    def list_published_relations(self, work_id: str) -> list[WorkKnowledgeProposal]:
        return self._repo.list_proposals(
            work_id=work_id,
            proposal_type='character_relation',
            status='published',
        )

    def list_published_plot_events(self, work_id: str) -> list[WorkKnowledgeProposal]:
        return self._repo.list_proposals(
            work_id=work_id,
            proposal_type='plot_event',
            status='published',
        )

    def list_published_world_rules(self, work_id: str) -> list[WorkKnowledgeProposal]:
        return self._repo.list_proposals(
            work_id=work_id,
            proposal_type='world_rule',
            status='published',
        )

    def list_review_queue(self) -> list[WorkKnowledgeProposal]:
        return self._repo.list_proposals(status='candidate')

    def list_review_queue_page(self, *, page: int = 1, page_size: int = 50, search: str = "") -> dict:
        if hasattr(self._repo, "list_proposals_page"):
            rows, total = self._repo.list_proposals_page(
                status="candidate",
                page=page,
                page_size=page_size,
                search=search,
            )
        else:
            all_rows = self._repo.list_proposals(status="candidate")
            normalized = search.strip().lower()
            filtered = [
                item for item in all_rows
                if not normalized or normalized in ' '.join(
                    str(value or '')
                    for value in (
                        item.id,
                        item.work_id,
                        item.source_chapter_id,
                        item.proposal_type,
                        item.subject,
                        item.relation,
                        item.object_name,
                        item.evidence,
                        item.created_by,
                    )
                ).lower()
            ]
            total = len(filtered)
            rows = filtered[(page - 1) * page_size : page * page_size]
        return {
            "items": rows,
            "meta": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": ceil(total / page_size) if total else 0,
                "search": search,
            },
        }

    def resolve_review(
        self,
        proposal_id: str,
        *,
        action: str,
        reviewer_id: str,
    ) -> WorkKnowledgeProposal:
        proposal = self._repo.get_proposal(proposal_id)
        if proposal is None:
            raise NotFoundException('Knowledge proposal not found')
        if action != 'publish':
            raise ValidationException('Only publish is supported')
        published = WorkKnowledgeProposal(
            id=uuid4().hex,
            work_id=proposal.work_id,
            source_chapter_id=proposal.source_chapter_id,
            proposal_type=proposal.proposal_type,
            subject=proposal.subject,
            relation=proposal.relation,
            object_name=proposal.object_name,
            evidence=proposal.evidence,
            payload=dict(proposal.payload),
            status='published',
            revision_of=proposal.id,
            created_by=proposal.created_by,
            reviewed_by=reviewer_id,
        )
        return self._repo.save_proposal(published)

    @staticmethod
    def _infer_subject_object(evidence: str, relation: str) -> tuple[str, str]:
        normalized = (evidence or '').strip()
        marker = f' {relation} '
        if marker in normalized:
            left, right = normalized.split(marker, 1)
            return left.strip(), right.strip()
        parts = normalized.split()
        if len(parts) >= 2:
            return parts[0], parts[-1]
        return '', ''
