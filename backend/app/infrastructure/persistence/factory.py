from app.application.services.ai_service import AIService
from app.application.services.ai_workspace_service import AIWorkspaceService
from app.application.services.agent_runtime_service import AgentRuntimeService
from app.application.services.character_calibration_service import CharacterCalibrationService
from app.application.services.canonical_content_service import CanonicalContentService
from app.application.services.content_distribution_service import ContentDistributionService
from app.application.services.dashboard_service import DashboardService
from app.application.services.event_delivery_service import EventDeliveryService
from app.application.services.engine_service import EngineService
from app.application.services.job_service import JobService
from app.application.services.interactive_browser_service import InteractiveBrowserService
from app.application.services.novel_agent_service import NovelAgentService
from app.application.services.novel_app_service import NovelAppService
from app.application.services.provider_platform_service import ProviderPlatformService
from app.application.services.source_complement_app_service import SourceComplementAppService
from app.application.services.source_build_agent import SourceBuildAgent
from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
from app.application.services.source_build_audit_service import SourceBuildAuditService
from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
from app.application.services.source_build_service import SourceBuildService
from app.application.services.source_health_admin_service import SourceHealthAdminService
from app.application.services.source_health_classifier_service import SourceHealthClassifierService
from app.application.services.source_health_service import SourceHealthService
from app.application.services.source_read_service import SourceReadService
from app.application.services.source_review_service import SourceReviewService
from app.application.services.source_probe_service import SourceProbeService
from app.application.services.source_routing_service import SourceRoutingService
from app.application.services.source_service import SourceAppService
from app.application.services.source_runtime_service import SourceRuntimeService
from app.application.services.system_settings_service import SystemSettingsService
from app.application.services.translation_service import TranslationService
from app.application.services.work_knowledge_service import WorkKnowledgeService
from app.core.config import settings
from app.infrastructure.browser.playwright_driver import PlaywrightBrowserDriver
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher
from app.infrastructure.persistence.sqlite.ai_runtime_repo_impl import SQLiteAIRuntimeRepository
from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
from app.infrastructure.persistence.sqlite.agent_runtime_repo_impl import SQLiteAgentRuntimeRepository
from app.infrastructure.persistence.sqlite.novel_runtime_repo_impl import SQLiteNovelRuntimeRepository
from app.infrastructure.persistence.sqlite.event_delivery_repo_impl import SQLiteEventDeliveryRepository
from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository
from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from app.infrastructure.providers.registry import ProviderRegistry, ProviderSelection
from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
from app.infrastructure.persistence.sqlite.canonical_content_repo_impl import SQLiteCanonicalContentRepository
from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
from app.infrastructure.persistence.sqlite.source_health_repo_impl import SQLiteSourceHealthRepository
from app.infrastructure.persistence.sqlite.source_review_repo_impl import SQLiteSourceReviewRepository
from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
from app.infrastructure.persistence.sqlite.system_settings_repo_impl import SQLiteSystemSettingsRepository
from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import SQLiteInteractiveBrowserRepository
from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import (
    SQLiteTranslationRuntimeRepository,
)
from app.infrastructure.persistence.sqlite.work_knowledge_repo_impl import SQLiteWorkKnowledgeRepository


def build_auth_repository() -> SQLiteAuthRepository:
    bootstrap_sqlite()
    return SQLiteAuthRepository()


def build_job_service() -> JobService:
    bootstrap_sqlite()
    return JobService(SQLiteJobRepository())


def build_job_repository() -> SQLiteJobRepository:
    bootstrap_sqlite()
    return SQLiteJobRepository()


def build_agent_runtime_service() -> AgentRuntimeService:
    bootstrap_sqlite()
    return AgentRuntimeService(SQLiteAgentRuntimeRepository())


def build_source_repository() -> SQLiteSourceRepository:
    bootstrap_sqlite()
    return SQLiteSourceRepository()


def build_source_health_repository() -> SQLiteSourceHealthRepository:
    bootstrap_sqlite()
    return SQLiteSourceHealthRepository()


def build_source_runtime_repository() -> SQLiteSourceRuntimeRepository:
    bootstrap_sqlite()
    return SQLiteSourceRuntimeRepository()


def build_source_review_repository() -> SQLiteSourceReviewRepository:
    bootstrap_sqlite()
    return SQLiteSourceReviewRepository()


def build_canonical_content_repository() -> SQLiteCanonicalContentRepository:
    bootstrap_sqlite()
    return SQLiteCanonicalContentRepository()


def build_provider_repository() -> SQLiteProviderRepository:
    bootstrap_sqlite()
    return SQLiteProviderRepository()


def build_system_settings_repository() -> SQLiteSystemSettingsRepository:
    bootstrap_sqlite()
    return SQLiteSystemSettingsRepository()


def build_interactive_browser_repository() -> SQLiteInteractiveBrowserRepository:
    bootstrap_sqlite()
    return SQLiteInteractiveBrowserRepository()


def build_source_runtime_service() -> SourceRuntimeService:
    return SourceRuntimeService(
        build_source_runtime_repository(),
        audit=build_auth_repository(),
    )


def build_source_review_service() -> SourceReviewService:
    return SourceReviewService(build_source_review_repository())


def build_canonical_content_service() -> CanonicalContentService:
    return CanonicalContentService(build_canonical_content_repository())


def build_content_distribution_service() -> ContentDistributionService:
    return ContentDistributionService(build_canonical_content_repository())


def build_source_build_service() -> SourceBuildService:
    return SourceBuildService(
        build_job_service(),
        build_source_runtime_repository(),
    )


def build_source_build_audit_service() -> SourceBuildAuditService:
    return SourceBuildAuditService(
        runtime_repo=build_source_runtime_repository(),
        probe_service_factory=build_source_probe_service,
        build_service=build_source_build_service(),
        review_service=build_source_review_service(),
        interactive_browser_service=build_interactive_browser_service(),
    )


def build_source_health_service() -> SourceHealthService:
    return SourceHealthService(
        build_source_runtime_repository(),
        review_service=build_source_review_service(),
        build_service=build_source_build_service(),
    )


def build_source_build_agent() -> SourceBuildAgent:
    return SourceBuildAgent(review_service=build_source_review_service())


def build_source_build_runtime_service(*, use_ai_repair: bool = True) -> SourceBuildRuntimeService:
    return SourceBuildRuntimeService(
        runtime_repo=build_source_runtime_repository(),
        agent_runtime=build_agent_runtime_service(),
        build_agent=build_source_build_agent(),
        probe_factory=build_source_probe_service,
        ai_repair_service=(build_source_build_ai_repair_service() if use_ai_repair else None),
        system_settings_service=build_system_settings_service(),
        review_service=build_source_review_service(),
    )


def build_source_probe_service() -> SourceProbeService:
    # Health probes must fail fast: runtime reads can keep their normal retry
    # budget, while batch probing thousands of sources cannot spend 45+ seconds
    # on each unreachable endpoint.
    return SourceProbeService(
        fetcher=LegadoBookSourceFetcher(
            timeout=10,
            max_retries=0,
            max_concurrent=10,
        )
    )


def build_source_health_classifier_service() -> SourceHealthClassifierService:
    return SourceHealthClassifierService()


def build_source_health_admin_service() -> SourceHealthAdminService:
    return SourceHealthAdminService(
        source_repo=build_source_repository(),
        health_repo=build_source_health_repository(),
        probe_service=build_source_probe_service(),
        classifier=build_source_health_classifier_service(),
    )


def build_source_routing_service() -> SourceRoutingService:
    return SourceRoutingService(health_repo=build_source_health_repository())


def build_source_service() -> SourceAppService:
    return SourceAppService(build_source_repository())


def build_source_read_service() -> SourceReadService:
    return SourceReadService(
        build_source_repository(),
        LegadoBookSourceFetcher(),
        routing_service=build_source_routing_service(),
    )


def build_source_complement_service() -> SourceComplementAppService:
    return SourceComplementAppService(build_source_repository(), LegadoBookSourceFetcher())


def build_dashboard_service() -> DashboardService:
    return DashboardService(build_source_repository())


def build_event_delivery_service() -> EventDeliveryService:
    bootstrap_sqlite()
    return EventDeliveryService(SQLiteEventDeliveryRepository())


def build_engine_service() -> EngineService:
    return EngineService()


class _AllowAllProviderQuotaLimiter:
    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        return None


def build_provider_registry() -> ProviderRegistry:
    provider_groups = ("default", "ai", "source_build", "translation", "novel")
    groups: dict[str, list[ProviderSelection]] = {}
    if settings.LLM_API_URL and settings.LLM_API_KEY:
        provider = OpenAICompatibleProvider(
            name=settings.LLM_PROVIDER_NAME,
            endpoint_url=settings.LLM_API_URL,
            api_key=settings.LLM_API_KEY,
        )
        groups = {
            key: [ProviderSelection(provider=provider, model=settings.LLM_MODEL)]
            for key in provider_groups
        }

    try:
        repo = build_provider_repository()
        accounts = {account.id: account for account in repo.list_configured_openai_providers()}
        if repo.has_routes():
            for group in provider_groups:
                routes = repo.list_routes(group)
                if not routes:
                    continue
                selections: list[ProviderSelection] = []
                for route in routes:
                    account = accounts.get(route.provider_account_id)
                    if account is None or not route.enabled or not route.model:
                        continue
                    selections.append(
                        ProviderSelection(
                            provider=OpenAICompatibleProvider(
                                name=account.name,
                                endpoint_url=account.base_url,
                                api_key=account.api_key,
                            ),
                            model=route.model,
                        )
                    )
                groups[group] = selections
        else:
            for account in accounts.values():
                provider = OpenAICompatibleProvider(
                    name=account.name,
                    endpoint_url=account.base_url,
                    api_key=account.api_key,
                )
                for group in provider_groups:
                    groups.setdefault(group, []).append(
                        ProviderSelection(provider=provider, model=account.default_model)
                    )
    except Exception:
        if not groups:
            return ProviderRegistry({})

    return ProviderRegistry(groups)


def build_provider_platform_service() -> ProviderPlatformService:
    return ProviderPlatformService(
        registry=build_provider_registry(),
        quota_limiter=_AllowAllProviderQuotaLimiter(),
        provider_repo=build_provider_repository(),
    )


def build_system_settings_service() -> SystemSettingsService:
    return SystemSettingsService(
        repo=build_system_settings_repository(),
        provider_registry=build_provider_registry(),
    )


def build_interactive_browser_service() -> InteractiveBrowserService:
    return InteractiveBrowserService(
        repo=build_interactive_browser_repository(),
        driver=PlaywrightBrowserDriver(
            chromium_path=settings.INTERACTIVE_BROWSER_CHROMIUM_PATH,
            xvfb_path=settings.INTERACTIVE_BROWSER_XVFB_PATH,
            x11vnc_path=settings.INTERACTIVE_BROWSER_X11VNC_PATH,
            websockify_path=settings.INTERACTIVE_BROWSER_WEBSOCKIFY_PATH,
        ),
        settings=build_system_settings_service(),
        profile_root=settings.INTERACTIVE_BROWSER_PROFILE_ROOT,
    )


def build_ai_runtime_repository() -> SQLiteAIRuntimeRepository:
    bootstrap_sqlite()
    return SQLiteAIRuntimeRepository()


def build_translation_runtime_repository() -> SQLiteTranslationRuntimeRepository:
    bootstrap_sqlite()
    return SQLiteTranslationRuntimeRepository()


def build_work_knowledge_repository() -> SQLiteWorkKnowledgeRepository:
    bootstrap_sqlite()
    return SQLiteWorkKnowledgeRepository()


def build_novel_runtime_repository() -> SQLiteNovelRuntimeRepository:
    bootstrap_sqlite()
    return SQLiteNovelRuntimeRepository()


def build_ai_service() -> AIService:
    return AIService(
        platform=build_provider_platform_service(),
        repo=build_ai_runtime_repository(),
    )


def build_ai_workspace_service() -> AIWorkspaceService:
    bootstrap_sqlite()
    return AIWorkspaceService(
        platform=build_provider_platform_service(),
        conversations=SQLiteAIConversationRepository(),
        sources=build_source_runtime_repository(),
        ai_tasks=build_ai_runtime_repository(),
        audit=build_auth_repository(),
    )


def build_source_build_ai_repair_service() -> SourceBuildAIRepairService:
    return SourceBuildAIRepairService(
        ai_service=build_ai_service(),
        platform=build_provider_platform_service(),
        agent_runtime=build_agent_runtime_service(),
    )


def build_character_calibration_service() -> CharacterCalibrationService:
    return CharacterCalibrationService(ai_service=build_ai_service())


def build_translation_service() -> TranslationService:
    return TranslationService(
        platform=build_provider_platform_service(),
        repo=build_translation_runtime_repository(),
        canonical_repo=build_canonical_content_repository(),
    )


def build_work_knowledge_service() -> WorkKnowledgeService:
    return WorkKnowledgeService(repo=build_work_knowledge_repository())


def build_novel_app_service() -> NovelAppService:
    return NovelAppService(repo=build_novel_runtime_repository())


def build_novel_agent_service() -> NovelAgentService:
    return NovelAgentService(
        platform=build_provider_platform_service(),
        repo=build_novel_runtime_repository(),
    )


# Compatibility aliases for legacy scheduler/tests that still import these names.
def get_source_repo() -> SQLiteSourceRepository:
    return build_source_repository()


def get_user_repo() -> SQLiteAuthRepository:
    return build_auth_repository()
