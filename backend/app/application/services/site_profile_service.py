from dataclasses import dataclass, field


@dataclass(frozen=True)
class SiteProfile:
    site_id: str
    dom_signatures: set[str] = field(default_factory=set)
    template_patch: dict | None = None
    fixture_coverage: float = 0.0
    confidence: float = 0.0
    risk_level: str = 'medium'
    outcome_tags: tuple[str, ...] = ()

    def matches(self, evidence: dict) -> bool:
        dom_signature = str(evidence.get('dom_signature') or '').strip()
        return bool(dom_signature) and dom_signature in self.dom_signatures


class SiteProfileService:
    def build_outcome_tags(self, profile: SiteProfile, *, matched: bool) -> tuple[str, ...]:
        tags = [
            f'site:{profile.site_id}',
            f'risk:{profile.risk_level}',
            f'fixture_coverage:{round(profile.fixture_coverage, 2):.2f}',
            f'confidence:{round(profile.confidence, 2):.2f}',
        ]
        if matched:
            tags.append('match:dom_signature')
        if profile.template_patch:
            tags.append('pattern:template_patch')
        tags.extend(profile.outcome_tags)
        return tuple(tags)

    def apply_human_correction(
        self,
        profile: SiteProfile,
        *,
        dom_signature: str,
        patch: dict,
    ) -> SiteProfile:
        return SiteProfile(
            site_id=profile.site_id,
            dom_signatures={*profile.dom_signatures, dom_signature},
            template_patch=patch,
            fixture_coverage=max(profile.fixture_coverage, 1.0),
            confidence=max(profile.confidence, 0.95),
            risk_level=profile.risk_level,
            outcome_tags=(*profile.outcome_tags, 'review:approved'),
        )
