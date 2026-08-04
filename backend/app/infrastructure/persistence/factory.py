import asyncio
from pathlib import Path
from threading import Lock
from functools import partial

from app.application.services.ai_service import AIService
from app.application.services.ai_authorization_service import AIConversationAuthorizationService
from app.application.services.ai_workspace_service import AIWorkspaceService
from app.application.services.agent_runtime_service import AgentRuntimeService
from app.application.services.character_calibration_service import CharacterCalibrationService
from app.application.services.canonical_content_service import CanonicalContentService
from app.application.services.content_distribution_service import ContentDistributionService
from app.application.services.dashboard_service import DashboardService
from app.application.services.event_delivery_service import EventDeliveryService
from app.application.services.engine_service import EngineService
from app.application.services.evidence_service import EvidenceService
from app.application.services.job_service import JobService
from app.application.services.maintenance_service import MaintenanceService
from app.application.services.interactive_browser_service import InteractiveBrowserService
from app.application.services.interactive_browser_supervisor import InteractiveBrowserSupervisor
from app.application.services.novel_agent_service import NovelAgentService
from app.application.services.novel_agent_app_service import NovelAgentAppService
from app.application.services.novel_cache_service import NovelCacheService
from app.application.services.novel_ingestion_service import NovelIngestionService
from app.application.services.novel_model_selection_service import NovelModelSelectionService
from app.application.services.novel_analysis_pipeline_service import NovelAnalysisPipelineService
from app.application.services.novel_analysis_audit_service import NovelAnalysisAuditService
from app.application.services.novel_analysis_task_service import NovelAnalysisTaskService
from app.application.services.narrative_knowledge_service import NarrativeKnowledgeService
from app.application.services.novel_app_service import NovelAppService
from app.application.services.provider_platform_service import ProviderPlatformService
from app.application.ports.provider import PROVIDER_ROUTE_GROUPS
from app.application.services.source_complement_app_service import SourceComplementAppService
from app.application.services.source_build_agent import SourceBuildAgent
from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
from app.application.services.source_build_audit_service import SourceBuildAuditService
from app.application.services.source_build_runtime_service import SourceBuildRuntimeService
from app.application.services.source_build_service import SourceBuildService
from app.application.services.source_joint_test_tool_executor import SourceJointTestToolExecutor
from app.application.services.source_to_insight_acceptance_service import SourceToInsightAcceptanceService
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
from app.application.services.work_ingestion_service import WorkIngestionService
from app.application.services.novel_analysis_tool_executor import NovelAnalysisToolExecutor
from app.application.services.novel_understanding.retriever import RAGRetriever
from app.core.config import settings
from app.infrastructure.cache.memory_cache import MemoryCacheProvider
from app.infrastructure.browser.playwright_driver import PlaywrightBrowserDriver
from app.infrastructure.browser.interactive_probe import run_browser_probe
from app.infrastructure.http.outbound import SafeAsyncHttpClient, SafeWebhookSender
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher
from app.infrastructure.crawler.source_fetcher import SourceFetcher
from app.infrastructure.legado.engine.evaluator import evaluate_source_rules
from app.infrastructure.legado.engine.harness import run_rule_harness
from app.infrastructure.legado.engine.repairer import repair_source_rules
from app.infrastructure.legado.engine.quality_gate import evaluate_runtime_health
from app.infrastructure.persistence.sqlite.ai_runtime_repo_impl import SQLiteAIRuntimeRepository
from app.infrastructure.persistence.sqlite.ai_conversation_repo_impl import SQLiteAIConversationRepository
from app.infrastructure.persistence.sqlite.ai_authorization_repo_impl import SQLiteAIAuthorizationRepository
from app.infrastructure.persistence.sqlite.agent_runtime_repo_impl import SQLiteAgentRuntimeRepository
from app.infrastructure.persistence.sqlite.novel_runtime_repo_impl import SQLiteNovelRuntimeRepository
from app.infrastructure.persistence.sqlite.novel_model_preference_repo_impl import SQLiteNovelModelPreferenceRepository
from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
from app.infrastructure.persistence.sqlite.novel_db_migrator import migrate_novel_database
from app.infrastructure.novel_ingestion.url_security import NovelUrlPolicy
from app.infrastructure.persistence.sqlite.novel_analysis_task_repo_impl import SQLiteNovelAnalysisTaskRepository
from app.infrastructure.persistence.sqlite.narrative_knowledge_repo_impl import SQLiteNarrativeKnowledgeRepository
from app.infrastructure.persistence.sqlite.event_delivery_repo_impl import SQLiteEventDeliveryRepository
from app.infrastructure.persistence.sqlite.evidence_repo_impl import SQLiteEvidenceRepository
from app.infrastructure.persistence.sqlite.job_repo_impl import SQLiteJobRepository
from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository
from app.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from app.infrastructure.providers.factory import create_provider_adapter
from app.infrastructure.providers.registry import ProviderRegistry, ProviderSelection
from app.infrastructure.persistence.sqlite.auth_repo_impl import SQLiteAuthRepository
from app.infrastructure.persistence.sqlite.bootstrap import ensure_sqlite_bootstrap
from app.infrastructure.persistence.sqlite.canonical_content_repo_impl import SQLiteCanonicalContentRepository
from app.infrastructure.persistence.sqlite.source_repo_impl import SQLiteSourceRepository
from app.infrastructure.persistence.sqlite.source_health_repo_impl import SQLiteSourceHealthRepository
from app.infrastructure.persistence.sqlite.source_review_repo_impl import SQLiteSourceReviewRepository
from app.infrastructure.persistence.sqlite.source_runtime_repo_impl import SQLiteSourceRuntimeRepository
from app.infrastructure.persistence.sqlite.system_settings_repo_impl import SQLiteSystemSettingsRepository
from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.infrastructure.persistence.sqlite.interactive_browser_repo_impl import SQLiteInteractiveBrowserRepository
from app.infrastructure.persistence.sqlite.translation_runtime_repo_impl import (
    SQLiteTranslationRuntimeRepository,
)
from app.infrastructure.persistence.sqlite.quota_usage_repo_impl import SQLiteQuotaUsageRepository
from app.infrastructure.persistence.sqlite.work_knowledge_repo_impl import SQLiteWorkKnowledgeRepository
from app.infrastructure.vectorstores import DisabledVectorStore, PgVectorStore, QdrantVectorStore, SQLiteVectorStore


_interactive_browser_service_singleton: InteractiveBrowserSupervisor | None = None
_interactive_browser_service_lock = Lock()
_novel_cache_provider = MemoryCacheProvider()
_novel_cache_service: NovelCacheService | None = None
_novel_database = None
_novel_database_lock = asyncio.Lock()


def build_auth_repository() -> SQLiteAuthRepository:
    ensure_sqlite_bootstrap()
    return SQLiteAuthRepository()


def build_job_service() -> JobService:
    ensure_sqlite_bootstrap()
    return JobService(SQLiteJobRepository())


def build_job_repository() -> SQLiteJobRepository:
    ensure_sqlite_bootstrap()
    return SQLiteJobRepository()


def build_quota_usage_repository() -> SQLiteQuotaUsageRepository:
    ensure_sqlite_bootstrap()
    return SQLiteQuotaUsageRepository()


def build_agent_runtime_service() -> AgentRuntimeService:
    ensure_sqlite_bootstrap()
    return AgentRuntimeService(SQLiteAgentRuntimeRepository())


def build_source_repository() -> SQLiteSourceRepository:
    ensure_sqlite_bootstrap()
    return SQLiteSourceRepository()


def build_source_health_repository() -> SQLiteSourceHealthRepository:
    ensure_sqlite_bootstrap()
    return SQLiteSourceHealthRepository()


def build_source_runtime_repository() -> SQLiteSourceRuntimeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteSourceRuntimeRepository()


def build_source_review_repository() -> SQLiteSourceReviewRepository:
    ensure_sqlite_bootstrap()
    return SQLiteSourceReviewRepository()


def build_canonical_content_repository() -> SQLiteCanonicalContentRepository:
    ensure_sqlite_bootstrap()
    return SQLiteCanonicalContentRepository()


def build_evidence_repository() -> SQLiteEvidenceRepository:
    ensure_sqlite_bootstrap()
    return SQLiteEvidenceRepository()


def build_narrative_knowledge_repository() -> SQLiteNarrativeKnowledgeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteNarrativeKnowledgeRepository()


def build_novel_analysis_task_repository() -> SQLiteNovelAnalysisTaskRepository:
    ensure_sqlite_bootstrap()
    return SQLiteNovelAnalysisTaskRepository()


def build_provider_repository() -> SQLiteProviderRepository:
    ensure_sqlite_bootstrap()
    return SQLiteProviderRepository()


def build_system_settings_repository() -> SQLiteSystemSettingsRepository:
    ensure_sqlite_bootstrap()
    return SQLiteSystemSettingsRepository()


def build_interactive_browser_repository() -> SQLiteInteractiveBrowserRepository:
    ensure_sqlite_bootstrap()
    return SQLiteInteractiveBrowserRepository()


def build_source_runtime_service() -> SourceRuntimeService:
    return SourceRuntimeService(
        build_source_runtime_repository(),
        audit=build_auth_repository(),
        source_repo=build_source_repository(),
        source_probe=build_source_probe_service(),
        audit_workflow=build_source_audit_workflow_service(),
    )


def build_source_audit_workflow_service():
    from app.application.services.source_audit_workflow_service import SourceAuditWorkflowService

    return SourceAuditWorkflowService(
        build_source_runtime_repository(),
        build_source_build_service(),
    )


def build_source_review_service() -> SourceReviewService:
    return SourceReviewService(build_source_review_repository())


def build_canonical_content_service() -> CanonicalContentService:
    return CanonicalContentService(build_canonical_content_repository())


def build_evidence_service() -> EvidenceService:
    return EvidenceService(
        repo=build_evidence_repository(),
        canonical_repo=build_canonical_content_repository(),
    )


def build_narrative_knowledge_service() -> NarrativeKnowledgeService:
    return NarrativeKnowledgeService(
        repo=build_narrative_knowledge_repository(),
        evidence_service=build_evidence_service(),
    )


def build_novel_analysis_task_service() -> NovelAnalysisTaskService:
    return NovelAnalysisTaskService(build_novel_analysis_task_repository())


def build_novel_analysis_pipeline_service() -> NovelAnalysisPipelineService:
    return NovelAnalysisPipelineService(
        knowledge_service=build_narrative_knowledge_service(),
        evidence_service=build_evidence_service(),
        platform=build_provider_platform_service(),
        settings_service=build_system_settings_service(),
        decision_recorder=build_novel_analysis_task_repository(),
    )


def build_novel_analysis_audit_service() -> NovelAnalysisAuditService:
    return NovelAnalysisAuditService(
        build_evidence_repository(),
        build_narrative_knowledge_repository(),
        task_service=build_novel_analysis_task_service(),
    )


def build_work_ingestion_service() -> WorkIngestionService:
    canonical_repo = build_canonical_content_repository()
    return WorkIngestionService(
        reader=build_source_read_service(),
        source_repo=build_source_repository(),
        source_runtime_repo=build_source_runtime_repository(),
        source_health_repo=build_source_health_repository(),
        canonical_repo=canonical_repo,
        evidence_service=EvidenceService(build_evidence_repository(), canonical_repo),
    )


def build_novel_analysis_tool_executor() -> NovelAnalysisToolExecutor:
    return NovelAnalysisToolExecutor(
        ingestion_service=build_work_ingestion_service(),
        evidence_service=build_evidence_service(),
        agent_runtime=build_agent_runtime_service(),
        audit_service=build_novel_analysis_audit_service(),
        settings_service=build_system_settings_service(),
    )


def build_novel_analysis_tool_registry():
    from app.application.services.agent_tool_registry import AgentToolRegistry

    return AgentToolRegistry(
        novel_analysis_handlers=build_novel_analysis_tool_executor().handlers(),
    )


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
        health_evaluator=evaluate_runtime_health,
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
        page_tool_factory=lambda url: SourcePageToolExecutor(url, SafeAsyncHttpClient()),
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
    source_repository = build_source_repository()
    return SourceAppService(source_repository, SourceFetcher(source_repository=source_repository))


def build_source_read_service() -> SourceReadService:
    return SourceReadService(
        build_source_repository(),
        LegadoBookSourceFetcher(),
        routing_service=build_source_routing_service(),
    )


def build_source_complement_service() -> SourceComplementAppService:
    return SourceComplementAppService(build_source_repository(), LegadoBookSourceFetcher())


def build_source_to_insight_acceptance_service() -> SourceToInsightAcceptanceService:
    return SourceToInsightAcceptanceService(
        source_build_service=build_source_build_service(),
        source_build_runtime=build_source_build_runtime_service(),
        job_repository=build_job_repository(),
        reading_service=build_source_read_service(),
        complement_service=build_source_complement_service(),
        character_service=build_character_calibration_service(),
        source_repository=build_source_repository(),
        source_runtime_repository=build_source_runtime_repository(),
    )


def build_source_joint_test_tool_executor() -> SourceJointTestToolExecutor:
    return SourceJointTestToolExecutor(build_source_to_insight_acceptance_service())


def build_dashboard_service() -> DashboardService:
    return DashboardService(build_source_repository())


def build_event_delivery_service() -> EventDeliveryService:
    ensure_sqlite_bootstrap()
    return EventDeliveryService(SQLiteEventDeliveryRepository(), sender=SafeWebhookSender())


def build_maintenance_service() -> MaintenanceService:
    # Resolve the shared quota adapter lazily so tests and deployments can
    # replace the Redis-backed implementation without importing it into the
    # application layer.
    from app.core.redis_client import redis_client

    return MaintenanceService(
        source_repo=build_source_repository(),
        auth_repo=build_auth_repository(),
        quota_repo=build_quota_usage_repository(),
        quota_store=redis_client,
    )


def build_engine_service() -> EngineService:
    return EngineService(
        evaluator=evaluate_source_rules,
        repairer=repair_source_rules,
        harness=run_rule_harness,
    )


class _AllowAllProviderQuotaLimiter:
    def assert_allowed(self, quota_scope: tuple[str, str]) -> None:
        return None


def build_provider_registry() -> ProviderRegistry:
    provider_groups = PROVIDER_ROUTE_GROUPS
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
        accounts = {account.id: account for account in repo.list_configured_providers()}
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
                    selections.append(ProviderSelection(
                        provider=create_provider_adapter(
                            name=account.name,
                            endpoint_url=account.base_url,
                            api_key=account.api_key,
                            provider_type=account.provider_type,
                        ),
                        model=route.model,
                    ))
                groups[group] = selections
        else:
            for account in accounts.values():
                provider = create_provider_adapter(
                    name=account.name,
                    endpoint_url=account.base_url,
                    api_key=account.api_key,
                    provider_type=account.provider_type,
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
        provider_factory=lambda name, endpoint_url, api_key, provider_type="openai_compatible": create_provider_adapter(
            name=name,
            endpoint_url=endpoint_url,
            api_key=api_key,
            provider_type=provider_type,
        ),
    )


def build_openharness_service():
    from app.infrastructure.harness.openharness.engine import OpenHarnessEngineService

    return OpenHarnessEngineService(
        provider_platform=build_provider_platform_service(),
        agent_runtime=build_agent_runtime_service(),
    )


def build_system_settings_service() -> SystemSettingsService:
    return SystemSettingsService(
        repo=build_system_settings_repository(),
        provider_registry=build_provider_registry(),
        metrics_provider=SQLiteAgentRuntimeRepository(),
    )


def build_vector_store():
    """Build the configured novel vector backend without exposing credentials."""
    config = build_system_settings_service().get_novel_settings(include_secrets=True)
    backend = config.get("vector_backend", "disabled")
    if backend == "sqlite":
        return SQLiteVectorStore(session_factory=SessionLocal)
    if backend == "qdrant":
        return QdrantVectorStore(
            endpoint=config.get("endpoint", ""),
            collection=config.get("collection_prefix", "novel"),
            api_key=config.get("api_key", ""),
        )
    if backend == "pgvector":
        return PgVectorStore(session_factory=SessionLocal)
    return DisabledVectorStore()


def build_novel_cache_service() -> NovelCacheService:
    global _novel_cache_service
    ttl = int(build_system_settings_service().get_novel_settings().get("cache_ttl", 3600) or 0)
    if _novel_cache_service is None:
        _novel_cache_service = NovelCacheService(_novel_cache_provider, default_ttl=ttl)
    else:
        _novel_cache_service._default_ttl = ttl
    return _novel_cache_service


def build_interactive_browser_service() -> InteractiveBrowserSupervisor:
    global _interactive_browser_service_singleton
    if _interactive_browser_service_singleton is None:
        with _interactive_browser_service_lock:
            if _interactive_browser_service_singleton is None:
                _interactive_browser_service_singleton = InteractiveBrowserSupervisor(
                    lambda: InteractiveBrowserService(
                        repo=build_interactive_browser_repository(),
                        driver=PlaywrightBrowserDriver(
                            chromium_path=settings.INTERACTIVE_BROWSER_CHROMIUM_PATH,
                            xvfb_path=settings.INTERACTIVE_BROWSER_XVFB_PATH,
                            x11vnc_path=settings.INTERACTIVE_BROWSER_X11VNC_PATH,
                            websockify_path=settings.INTERACTIVE_BROWSER_WEBSOCKIFY_PATH,
                        ),
                        settings=build_system_settings_service(),
                        profile_root=settings.INTERACTIVE_BROWSER_PROFILE_ROOT,
                        probe_runner=partial(run_browser_probe, probe_factory=SourceProbeService),
                    )
                )
    return _interactive_browser_service_singleton


def close_interactive_browser_supervisor() -> None:
    """Close the cached browser owner loop without creating a new supervisor."""
    global _interactive_browser_service_singleton
    with _interactive_browser_service_lock:
        supervisor = _interactive_browser_service_singleton
        if supervisor is None:
            return
        try:
            supervisor.close()
        finally:
            if _interactive_browser_service_singleton is supervisor:
                _interactive_browser_service_singleton = None


def build_ai_runtime_repository() -> SQLiteAIRuntimeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteAIRuntimeRepository()


def build_ai_authorization_repository() -> SQLiteAIAuthorizationRepository:
    ensure_sqlite_bootstrap()
    return SQLiteAIAuthorizationRepository()


def build_translation_runtime_repository() -> SQLiteTranslationRuntimeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteTranslationRuntimeRepository()


def build_work_knowledge_repository() -> SQLiteWorkKnowledgeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteWorkKnowledgeRepository()


def build_novel_runtime_repository() -> SQLiteNovelRuntimeRepository:
    ensure_sqlite_bootstrap()
    return SQLiteNovelRuntimeRepository()


def build_novel_model_preference_repository() -> SQLiteNovelModelPreferenceRepository:
    ensure_sqlite_bootstrap()
    return SQLiteNovelModelPreferenceRepository()


async def build_novel_repository() -> SqliteNovelRepository:
    """Return the shared async repository for the standalone novel database."""
    global _novel_database
    async with _novel_database_lock:
        if _novel_database is None:
            import aiosqlite

            database_path = Path(settings.NOVEL_DB_PATH)
            database_path.parent.mkdir(parents=True, exist_ok=True)
            _novel_database = await aiosqlite.connect(database_path.as_posix())
            schema_path = Path(__file__).resolve().parents[2] / "database_migrations" / "novel_schema.sql"
            async with _novel_database.execute("PRAGMA table_info(novels)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if columns and "owner_scope" not in columns:
                await migrate_novel_database(_novel_database)
            else:
                await _novel_database.executescript(schema_path.read_text(encoding="utf-8"))
                await migrate_novel_database(_novel_database)
    return SqliteNovelRepository(_novel_database)


def build_novel_adaptive_learning_service(repo):
    """Build the conservative learning facade over the shared novel repository."""
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService

    return AdaptiveLearningService(repo=repo)


async def close_novel_repository() -> None:
    global _novel_database
    async with _novel_database_lock:
        if _novel_database is not None:
            await _novel_database.close()
            _novel_database = None


def build_ai_service() -> AIService:
    return AIService(
        platform=build_provider_platform_service(),
        repo=build_ai_runtime_repository(),
    )


def build_ai_conversation_service() -> AIWorkspaceService:
    """Build only the dependencies needed to read and manage conversations.

    Conversation history and authorization state do not need provider, source,
    or analysis-tool initialization. Keeping this path separate prevents a
    read request from paying the startup cost of the full AI workspace.
    """
    ensure_sqlite_bootstrap()
    audit = build_auth_repository()
    return AIWorkspaceService(
        platform=None,
        conversations=SQLiteAIConversationRepository(),
        sources=None,
        ai_tasks=None,
        audit=audit,
        authorization_service=AIConversationAuthorizationService(
            repo=build_ai_authorization_repository(),
            audit=audit,
        ),
    )


def build_ai_workspace_service(*, novel_agent_app=None) -> AIWorkspaceService:
    ensure_sqlite_bootstrap()
    authorization = AIConversationAuthorizationService(
        repo=build_ai_authorization_repository(),
        audit=build_auth_repository(),
    )
    return AIWorkspaceService(
        platform=build_provider_platform_service(),
        conversations=SQLiteAIConversationRepository(),
        sources=build_source_runtime_repository(),
        ai_tasks=build_ai_runtime_repository(),
        audit=build_auth_repository(),
        source_runtime=build_source_runtime_service(),
        novel_tool_executor=build_novel_analysis_tool_executor(),
        source_joint_test_executor=build_source_joint_test_tool_executor(),
        authorization_service=authorization,
        novel_agent_app=novel_agent_app,
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
    app_service = build_novel_agent_app_service()
    return NovelAgentService(
        platform=build_provider_platform_service(),
        repo=build_novel_runtime_repository(),
        app_service=app_service,
    )


def build_novel_ingestion_service(*, repo, source_reader=None, runtime_repo=None) -> NovelIngestionService:
    return NovelIngestionService(
        repo=repo,
        source_reader=source_reader or build_source_read_service(),
        runtime_repo=runtime_repo or build_novel_runtime_repository(),
        url_policy=NovelUrlPolicy(),
    )


def build_novel_agent_app_service(
    *,
    novel_repo=None,
    retriever=None,
    conversations=None,
    model_selection=None,
    cache=None,
    agent_runtime=None,
    tool_registry=None,
    enabled_tool_categories=None,
) -> NovelAgentAppService:
    """Assemble the shared novel assistant around existing boundaries."""
    ensure_sqlite_bootstrap()
    if enabled_tool_categories is None:
        configured = build_system_settings_service().get_novel_settings().get("agent_permissions", {})
        enabled_tool_categories = {
            category for category, enabled in configured.items() if enabled
        }
    return NovelAgentAppService(
        platform=build_provider_platform_service(),
        conversations=conversations or SQLiteAIConversationRepository(),
        novel_repo=novel_repo,
        retriever=retriever,
        model_selection=model_selection or NovelModelSelectionService(
            preferences=build_novel_model_preference_repository(),
            routes=build_provider_registry(),
        ),
        cache=cache or build_novel_cache_service(),
        agent_runtime=agent_runtime or build_agent_runtime_service(),
        tool_registry=tool_registry,
        enabled_tool_categories=enabled_tool_categories,
    )


async def build_scoped_novel_agent_app_service() -> NovelAgentAppService:
    """Build the novel assistant with the shared owner-scoped novel context."""
    repo = await build_novel_repository()
    novel_settings = build_system_settings_service().get_novel_settings()
    retriever = RAGRetriever(
        repo,
        vector_store=build_vector_store(),
        similarity_threshold=float(novel_settings.get("threshold", 0.0) or 0.0),
    )
    return build_novel_agent_app_service(novel_repo=repo, retriever=retriever)
