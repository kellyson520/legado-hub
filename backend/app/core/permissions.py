from enum import Enum


DEFAULT_ROLE_NAME = "admin"


class Permission(str, Enum):
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    ROLES_READ = "roles.read"
    ROLES_WRITE = "roles.write"
    PERMISSIONS_READ = "permissions.read"
    API_KEYS_READ = "api_keys.read"
    API_KEYS_WRITE = "api_keys.write"
    BOOK_SOURCES_READ = "book_sources.read"
    BOOK_SOURCES_WRITE = "book_sources.write"
    RSS_SOURCES_READ = "rss_sources.read"
    RSS_SOURCES_WRITE = "rss_sources.write"
    SUBSCRIPTIONS_READ = "subscriptions.read"
    SUBSCRIPTIONS_WRITE = "subscriptions.write"
    FILTER_RULES_READ = "filter_rules.read"
    FILTER_RULES_WRITE = "filter_rules.write"
    ENGINE_GENERATE = "engine.generate"
    ENGINE_EVALUATE = "engine.evaluate"
    ENGINE_REPAIR = "engine.repair"
    ENGINE_REGRESSION = "engine.regression"
    ENGINE_DEPLOY = "engine.deploy"
    ENGINE_TEST = "engine.test"
    DASHBOARD_READ = "dashboard.read"
    HEALTH_CHECK = "health.check"
    EXPORT_READ = "export.read"
    SYSTEM_AUDIT_READ = "system.audit.read"
    SYSTEM_JOBS_MANAGE = "system.jobs.manage"
    SYSTEM_SETTINGS_MANAGE = "system.settings.manage"
    AI_RUN = "ai.run"
    TRANSLATION_RUN = "translation.run"
    NOVEL_MANAGE = "novel.manage"
    JOBS_SUBMIT = "jobs.submit"
    EVENTS_READ = "events.read"
    AGENT_RUNS_READ = "agent_runs.read"
    AGENT_RUNS_WRITE = "agent_runs.write"
    CLIENT_CAPABILITIES_READ = "client.capabilities.read"
    SOURCE_SUBMIT = "source.submit"
    READ_WORK = "read.work"
    READ_TOC = "read.toc"
    READ_CHAPTER = "read.chapter"


def build_permission_matrix() -> list[str]:
    return [permission.value for permission in Permission]
