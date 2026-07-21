from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False, default="")
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class RoleModel(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=False, default="")


class PermissionModel(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)


class UserRoleModel(Base):
    __tablename__ = "user_roles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    key_hash = Column(String, nullable=False, unique=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ApiKeyPermissionModel(Base):
    __tablename__ = "api_key_permissions"

    api_key_id = Column(Integer, ForeignKey("api_keys.id"), primary_key=True)
    permission_name = Column(String, primary_key=True)


class QuotaUsageModel(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("api_key_id", "date", name="ux_quota_usage_api_key_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False, index=True)
    date = Column(String, nullable=False, index=True)
    fetch_count = Column(Integer, nullable=False, default=0)
    ai_chars = Column(Integer, nullable=False, default=0)
    storage_mb = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobModel(Base):
    __tablename__ = 'jobs'

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    payload = Column(Text, nullable=False, default='{}')
    idempotency_key = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default='queued', index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    worker_id = Column(String, nullable=True)
    lease_token = Column(String, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    available_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class EventDeliveryModel(Base):
    __tablename__ = 'event_deliveries'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'dedupe_key', name='ux_event_deliveries_tenant_dedupe_key'),
    )

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    target_url = Column(Text, nullable=False)
    body = Column(Text, nullable=False, default='{}')
    headers_json = Column(Text, nullable=False, default='{}')
    dedupe_key = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default='pending', index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class EventDeliveryAttemptModel(Base):
    __tablename__ = 'event_delivery_attempts'
    __table_args__ = (
        UniqueConstraint('event_id', 'attempt_no', name='ux_event_delivery_attempts_event_attempt'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey('event_deliveries.event_id'), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False)
    delivered = Column(Boolean, nullable=False, default=False)
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class JobEventModel(Base):
    __tablename__ = 'job_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AgentRunModel(Base):
    __tablename__ = 'agent_runs'

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    agent_kind = Column(String, nullable=False, index=True)
    input_payload = Column(Text, nullable=False, default='{}')
    owner_scope = Column(String, nullable=False, default='legacy', index=True)
    book_id = Column(Integer, nullable=True, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    entrypoint = Column(String, nullable=False, default='')
    conversation_id = Column(String, nullable=False, default='', index=True)
    provider_name = Column(String, nullable=False, default='')
    model_name = Column(String, nullable=False, default='')
    attempt_count = Column(Integer, nullable=False, default=0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost = Column(Float, nullable=False, default=0.0)
    tool_names = Column(Text, nullable=False, default='[]')
    evidence_ids = Column(Text, nullable=False, default='[]')
    status = Column(String, nullable=False, default='candidate', index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class ToolInvocationModel(Base):
    __tablename__ = 'tool_invocations'

    id = Column(String, primary_key=True)
    agent_run_id = Column(String, ForeignKey('agent_runs.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)
    arguments = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class ToolResultModel(Base):
    __tablename__ = 'tool_results'

    id = Column(String, primary_key=True)
    tool_invocation_id = Column(String, ForeignKey('tool_invocations.id'), nullable=False, unique=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    data = Column(Text, nullable=False, default='{}')
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class ToolEvidenceModel(Base):
    __tablename__ = 'tool_evidence'

    id = Column(String, primary_key=True)
    tool_invocation_id = Column(String, ForeignKey('tool_invocations.id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    evidence_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=False, index=True)
    payload = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False, index=True)
    resource = Column(String, nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class BookSourceModel(Base):
    __tablename__ = "book_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bookSourceName = Column(String, nullable=False)
    bookSourceUrl = Column(String, nullable=False, unique=True, index=True)
    bookSourceGroup = Column(String, nullable=False, default="default")
    enabled = Column(Boolean, nullable=False, default=True)
    payload = Column(Text, nullable=False, default="{}")
    sourceStatus = Column(String, nullable=False, default="unknown")
    sourceOrigin = Column(Text, nullable=True)
    lastCheckTime = Column(DateTime, nullable=True)
    errorMsg = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RssSourceModel(Base):
    __tablename__ = "rss_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sourceName = Column(String, nullable=False)
    sourceUrl = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class FilterRuleModel(Base):
    __tablename__ = "filter_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    pattern = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class SourceDefinitionModel(Base):
    __tablename__ = "source_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False, index=True)
    source_key = Column(String, nullable=False, index=True)
    source_name = Column(String, nullable=False, default="")
    source_group = Column(String, nullable=False, default="default")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceVersionModel(Base):
    __tablename__ = "source_versions"

    id = Column(String, primary_key=True)
    source_definition_id = Column(Integer, ForeignKey("source_definitions.id"), nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    source_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    payload = Column(Text, nullable=False, default="{}")
    created_by = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)


class SourceTestRunModel(Base):
    __tablename__ = "source_test_runs"

    id = Column(String, primary_key=True)
    source_version_id = Column(String, ForeignKey("source_versions.id"), nullable=False, index=True)
    trigger = Column(String, nullable=False)
    score = Column(Integer, nullable=False, default=0)
    grade = Column(String, nullable=False, default="F")
    step_results = Column(Text, nullable=False, default="{}")
    diagnostics = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceRunStepModel(Base):
    __tablename__ = "source_run_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_run_id = Column(String, ForeignKey("source_test_runs.id"), nullable=False, index=True)
    step_name = Column(String, nullable=False)
    passed = Column(Boolean, nullable=False, default=False)
    elapsed_ms = Column(Integer, nullable=False, default=0)
    detail = Column(Text, nullable=False, default="{}")


class SourceDeploymentModel(Base):
    __tablename__ = "source_deployments"

    id = Column(String, primary_key=True)
    source_version_id = Column(String, ForeignKey("source_versions.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    quality_gate = Column(Text, nullable=False, default="{}")
    actor_id = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceHealthEventModel(Base):
    __tablename__ = "source_health_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_version_id = Column(String, ForeignKey("source_versions.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceHealthSnapshotModel(Base):
    __tablename__ = "source_health_snapshots"

    source_id = Column(Integer, primary_key=True)
    source_name = Column(String, nullable=False, default="")
    source_url = Column(Text, nullable=False, default="")
    health_status = Column(String, nullable=False, default="unknown", index=True)
    search_status = Column(String, nullable=False, default="unknown")
    toc_status = Column(String, nullable=False, default="unknown")
    content_status = Column(String, nullable=False, default="unknown")
    failure_reason = Column(String, nullable=False, default="")
    decision_confidence = Column(String, nullable=False, default="low")
    route_policy = Column(String, nullable=False, default="probe_only")
    route_score = Column(Float, nullable=False, default=0.0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_probe_at = Column(DateTime, nullable=True)
    next_probe_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")


class SourceProbeRunModel(Base):
    __tablename__ = "source_probe_runs"

    id = Column(String, primary_key=True)
    source_id = Column(Integer, nullable=False, index=True)
    source_name = Column(String, nullable=False, default="")
    probe_mode = Column(String, nullable=False, default="search_only")
    keyword = Column(String, nullable=False, default="")
    overall_status = Column(String, nullable=False, default="unknown", index=True)
    failure_reason = Column(String, nullable=False, default="")
    search_result = Column(Text, nullable=False, default="{}")
    toc_result = Column(Text, nullable=False, default="{}")
    content_result = Column(Text, nullable=False, default="{}")
    summary = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProviderAccountModel(Base):
    __tablename__ = "provider_accounts"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    provider_type = Column(String, nullable=False, index=True)
    base_url = Column(String, nullable=False)
    api_key = Column(Text, nullable=False, default="")
    default_model = Column(String, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProviderRouteModel(Base):
    __tablename__ = "provider_routes"
    __table_args__ = (
        UniqueConstraint("provider_group", "priority", name="ux_provider_routes_group_priority"),
    )

    id = Column(String, primary_key=True)
    provider_group = Column(String, nullable=False, index=True)
    provider_account_id = Column(String, ForeignKey("provider_accounts.id"), nullable=False, index=True)
    model = Column(String, nullable=False)
    priority = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class ProviderModelModel(Base):
    __tablename__ = "provider_models"

    id = Column(String, primary_key=True)
    provider_account_id = Column(String, ForeignKey("provider_accounts.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    capabilities = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class QuotaPolicyModel(Base):
    __tablename__ = "quota_policies"

    id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, index=True)
    daily_cost_limit = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AITaskModel(Base):
    __tablename__ = "ai_tasks"

    id = Column(String, primary_key=True)
    task_type = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False, index=True)
    provider_name = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, index=True)
    prompt_payload = Column(Text, nullable=False, default="{}")
    result_payload = Column(Text, nullable=False, default="{}")
    usage_payload = Column(Text, nullable=False, default="{}")
    cost_payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AIConversationModel(Base):
    __tablename__ = "ai_conversations"

    id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    owner_scope = Column(String, nullable=False, default="legacy", index=True)
    title = Column(String, nullable=False, default="")
    book_id = Column(Integer, nullable=True, index=True)
    entrypoint = Column(String, nullable=False, default="workspace")
    context_range = Column(String, nullable=False, default="book")
    model_ref = Column(String, nullable=True)
    knowledge_version = Column(String, nullable=False, default="")
    toolset_version = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AIConversationMessageModel(Base):
    __tablename__ = "ai_conversation_messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("ai_conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="chat")
    content = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="succeeded")
    tool_calls = Column(Text, nullable=False, default="[]")
    owner_scope = Column(String, nullable=False, default="legacy", index=True)
    entrypoint = Column(String, nullable=False, default="workspace")
    book_id = Column(Integer, nullable=True, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class TranslationTaskModel(Base):
    __tablename__ = "translation_tasks"

    id = Column(String, primary_key=True)
    actor_id = Column(String, nullable=False, index=True)
    source_language = Column(String, nullable=False, default="")
    target_language = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, index=True)
    provider_name = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    source_text = Column(Text, nullable=False, default="")
    result_text = Column(Text, nullable=False, default="")
    content_variant_id = Column(String, nullable=True, index=True)
    review_status = Column(String, nullable=False, default="candidate", index=True)
    memory_payload = Column(Text, nullable=False, default="{}")
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TranslationChunkModel(Base):
    __tablename__ = "translation_chunks"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("translation_tasks.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    source_text = Column(Text, nullable=False, default="")
    translated_text = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, index=True)
    provider_name = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    usage_payload = Column(Text, nullable=False, default="{}")
    attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class NovelIngestionModel(Base):
    __tablename__ = "novel_ingestions"

    id = Column(String, primary_key=True)
    owner_scope = Column(String, nullable=False, default="legacy", index=True)
    book_id = Column(Integer, nullable=True, index=True)
    title = Column(String, nullable=False, default="")
    source_text = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, default="")
    pipeline = Column(String, nullable=False, default="analysis")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class NovelTaskModel(Base):
    __tablename__ = "novel_tasks"

    id = Column(String, primary_key=True)
    novel_id = Column(String, ForeignKey("novel_ingestions.id"), nullable=False, index=True)
    owner_scope = Column(String, nullable=False, default="legacy", index=True)
    book_id = Column(Integer, nullable=True, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    actor_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    provider_name = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    pipeline = Column(String, nullable=False, default="analysis")
    result_payload = Column(Text, nullable=False, default="{}")
    usage_payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class NovelIndexStateModel(Base):
    __tablename__ = "novel_index_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_scope = Column(String, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    content_hash = Column(String, nullable=False, default="")
    knowledge_version = Column(String, nullable=False, default="")
    extraction_status = Column(String, nullable=False, default="pending")
    bm25_status = Column(String, nullable=False, default="pending")
    vector_status = Column(String, nullable=False, default="disabled")
    embedding_model = Column(String, nullable=False, default="")
    embedding_dimension = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class NovelReadingProgressModel(Base):
    __tablename__ = "novel_reading_progress"

    owner_scope = Column(String, primary_key=True)
    book_id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, nullable=False)
    offset_chars = Column(Integer, nullable=False, default=0)
    percent = Column(Float, nullable=False, default=0.0)
    theme = Column(String, nullable=False, default="paper")
    background = Column(Text, nullable=False, default="")
    font_size = Column(Integer, nullable=False, default=18)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class NovelVectorModel(Base):
    """Local vector payloads; vector similarity is calculated by the adapter."""

    __tablename__ = "novel_vectors"
    __table_args__ = (
        UniqueConstraint(
            "owner_scope", "book_id", "chapter_id", "knowledge_version",
            name="ux_novel_vectors_scope_book_chapter_version",
        ),
    )

    owner_scope = Column(String, primary_key=True)
    book_id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, primary_key=True)
    knowledge_version = Column(String, primary_key=True)
    vector = Column(Text, nullable=False, default="[]")
    payload = Column(Text, nullable=False, default="{}")


class NovelModelPreferenceModel(Base):
    __tablename__ = "novel_model_preferences"
    __table_args__ = (
        UniqueConstraint(
            "owner_scope", "scope_type", "scope_id", "task_type",
            name="ux_novel_model_preferences_scope_task",
        ),
    )

    owner_scope = Column(String, primary_key=True)
    scope_type = Column(String, primary_key=True)
    scope_id = Column(String, primary_key=True)
    task_type = Column(String, primary_key=True)
    model_ref = Column(String, nullable=False)
    provider_group = Column(String, nullable=False, default="novel")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CanonicalWorkModel(Base):
    __tablename__ = "canonical_works"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="", index=True)
    author = Column(String, nullable=False, default="", index=True)
    normalized_title = Column(String, nullable=False, default="", index=True)
    normalized_author = Column(String, nullable=False, default="", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class WorkAliasModel(Base):
    __tablename__ = "work_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_work_id = Column(String, ForeignKey("canonical_works.id"), nullable=False, index=True)
    alias = Column(String, nullable=False, default="")
    alias_type = Column(String, nullable=False, default="source")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceWorkModel(Base):
    __tablename__ = "source_works"

    id = Column(String, primary_key=True)
    canonical_work_id = Column(String, ForeignKey("canonical_works.id"), nullable=False, index=True)
    source_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="")
    author = Column(String, nullable=False, default="")
    normalized_title = Column(String, nullable=False, default="", index=True)
    normalized_author = Column(String, nullable=False, default="", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CanonicalChapterModel(Base):
    __tablename__ = "canonical_chapters"

    id = Column(String, primary_key=True)
    canonical_work_id = Column(String, ForeignKey("canonical_works.id"), nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False, default=0, index=True)
    title = Column(String, nullable=False, default="")
    normalized_title = Column(String, nullable=False, default="", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SourceChapterModel(Base):
    __tablename__ = "source_chapters"

    id = Column(String, primary_key=True)
    source_work_id = Column(String, ForeignKey("source_works.id"), nullable=False, index=True)
    canonical_chapter_id = Column(String, ForeignKey("canonical_chapters.id"), nullable=True, index=True)
    chapter_index = Column(Integer, nullable=False, default=0, index=True)
    title = Column(String, nullable=False, default="")
    normalized_title = Column(String, nullable=False, default="", index=True)
    chapter_url = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ChapterAlignmentModel(Base):
    __tablename__ = "chapter_alignments"

    id = Column(String, primary_key=True)
    canonical_chapter_id = Column(String, ForeignKey("canonical_chapters.id"), nullable=False, index=True)
    source_chapter_id = Column(String, ForeignKey("source_chapters.id"), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    evidence = Column(Text, nullable=False, default="{}")
    review_status = Column(String, nullable=False, default="accepted", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ContentVariantModel(Base):
    __tablename__ = "content_variants"

    id = Column(String, primary_key=True)
    canonical_chapter_id = Column(String, ForeignKey("canonical_chapters.id"), nullable=False, index=True)
    source_chapter_id = Column(String, ForeignKey("source_chapters.id"), nullable=False, index=True)
    source_id = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    health_status = Column(String, nullable=False, default="unknown", index=True)
    quality_score = Column(Float, nullable=False, default=0.0)
    coverage_score = Column(Float, nullable=False, default=0.0)
    freshness_score = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    is_verified = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RouteDecisionModel(Base):
    __tablename__ = "route_decisions"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    canonical_chapter_id = Column(String, ForeignKey("canonical_chapters.id"), nullable=False, index=True)
    selected_variant_id = Column(String, ForeignKey("content_variants.id"), nullable=True, index=True)
    fallback_count = Column(Integer, nullable=False, default=0)
    route_summary = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class WorkKnowledgeProposalModel(Base):
    __tablename__ = "work_knowledge_proposals"

    id = Column(String, primary_key=True)
    work_id = Column(String, nullable=False, index=True)
    source_chapter_id = Column(String, nullable=False, index=True)
    proposal_type = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False, default="")
    relation = Column(String, nullable=False, default="", index=True)
    object_name = Column(String, nullable=False, default="")
    evidence = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="candidate", index=True)
    revision_of = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=False, default="")
    reviewed_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)


class SourceReviewItemModel(Base):
    __tablename__ = "source_review_items"

    id = Column(String, primary_key=True)
    review_type = Column(String, nullable=False, index=True)
    source_version_id = Column(String, ForeignKey("source_versions.id"), nullable=True, index=True)
    source_url = Column(Text, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="candidate", index=True)
    created_by = Column(String, nullable=False, default="")
    reviewed_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
