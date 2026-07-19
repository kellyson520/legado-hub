from threading import Lock

from app.core.permissions import DEFAULT_ROLE_NAME, build_permission_matrix
from app.infrastructure.persistence.sqlite.session import Base, SessionLocal, engine

from . import schema as _schema
from .schema import PermissionModel, RoleModel, RolePermissionModel


_bootstrap_lock = Lock()
_bootstrapped_engine_url: str | None = None


def _ensure_sqlite_source_columns() -> None:
    required_columns = {
        "payload": "TEXT NOT NULL DEFAULT '{}'",
        "sourceStatus": "VARCHAR NOT NULL DEFAULT 'unknown'",
        "sourceOrigin": "TEXT",
        "lastCheckTime": "DATETIME",
        "errorMsg": "TEXT",
        "updated_at": "DATETIME",
    }
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(book_sources)").fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}
        for column, ddl in required_columns.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE book_sources ADD COLUMN {column} {ddl}")


def _ensure_sqlite_user_columns() -> None:
    required_columns = {
        "display_name": "VARCHAR NOT NULL DEFAULT ''",
        "last_login_at": "DATETIME",
    }
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}
        for column, ddl in required_columns.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {column} {ddl}")


def _ensure_sqlite_job_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()
        if not rows:
            return
        columns = {row[1] for row in rows}
        if "last_error" not in columns:
            connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN last_error TEXT")
        if "available_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN available_at DATETIME")
        if "lease_token" not in columns:
            connection.exec_driver_sql("ALTER TABLE jobs ADD COLUMN lease_token VARCHAR")
        duplicates = connection.exec_driver_sql(
            "SELECT tenant_id, idempotency_key, COUNT(*) FROM jobs "
            "WHERE idempotency_key IS NOT NULL "
            "GROUP BY tenant_id, idempotency_key HAVING COUNT(*) > 1"
        ).fetchall()
        if duplicates:
            tenant_id, idempotency_key, count = duplicates[0]
            raise RuntimeError(
                'Cannot enforce job idempotency: duplicate idempotency keys exist '
                f'for tenant {tenant_id!r}, key {idempotency_key!r} ({count} rows). '
                'Resolve duplicate jobs before restarting.'
            )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_tenant_idempotency_key "
            "ON jobs (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
        )


def _ensure_sqlite_translation_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(translation_tasks)").fetchall()
        if not rows:
            return
        columns = {row[1] for row in rows}
        if "content_variant_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE translation_tasks ADD COLUMN content_variant_id VARCHAR")
        if "review_status" not in columns:
            connection.exec_driver_sql("ALTER TABLE translation_tasks ADD COLUMN review_status VARCHAR NOT NULL DEFAULT 'candidate'")
        if "memory_payload" not in columns:
            connection.exec_driver_sql("ALTER TABLE translation_tasks ADD COLUMN memory_payload TEXT NOT NULL DEFAULT '{}'")


def _ensure_sqlite_provider_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(provider_accounts)").fetchall()
        if not rows:
            return
        columns = {row[1] for row in rows}
        if "api_key" not in columns:
            connection.exec_driver_sql("ALTER TABLE provider_accounts ADD COLUMN api_key TEXT NOT NULL DEFAULT ''")
        if "default_model" not in columns:
            connection.exec_driver_sql("ALTER TABLE provider_accounts ADD COLUMN default_model VARCHAR NOT NULL DEFAULT ''")
        if "activation_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE provider_accounts ADD COLUMN activation_at DATETIME")


def _ensure_sqlite_novel_analysis_columns() -> None:
    required_columns = {
        "task_id": "VARCHAR",
        "role": "VARCHAR NOT NULL DEFAULT 'adjudicator'",
        "evidence_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "provider_group": "VARCHAR",
        "provider_name": "VARCHAR",
        "model": "VARCHAR",
        "prompt_version": "VARCHAR",
        "policy_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(knowledge_adjudications)").fetchall()
        if not rows:
            return
        columns = {row[1] for row in rows}
        for column, ddl in required_columns.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE knowledge_adjudications ADD COLUMN {column} {ddl}"
                )


def _ensure_sqlite_ai_conversation_columns() -> None:
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(ai_conversation_messages)").fetchall()
        if rows and "metadata_payload" not in {row[1] for row in rows}:
            connection.exec_driver_sql("ALTER TABLE ai_conversation_messages ADD COLUMN metadata_payload TEXT NOT NULL DEFAULT '{}'")
        request_rows = connection.exec_driver_sql("PRAGMA table_info(ai_authorization_requests)").fetchall()
        if request_rows:
            request_columns = {row[1] for row in request_rows}
            if "claim_token" not in request_columns:
                connection.exec_driver_sql("ALTER TABLE ai_authorization_requests ADD COLUMN claim_token VARCHAR")
            if "claim_expires_at" not in request_columns:
                connection.exec_driver_sql("ALTER TABLE ai_authorization_requests ADD COLUMN claim_expires_at DATETIME")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_ai_authorization_requests_actor_conversation "
                "ON ai_authorization_requests (actor_id, conversation_id)"
            )
            duplicate_requests = connection.exec_driver_sql(
                "SELECT actor_id, conversation_id, id FROM ai_authorization_requests "
                "WHERE status IN ('pending', 'processing') "
                "ORDER BY actor_id, conversation_id, created_at DESC, id DESC"
            ).fetchall()
            seen_request_keys: set[tuple[str, str]] = set()
            for actor_id, conversation_id, request_id in duplicate_requests:
                key = (str(actor_id), str(conversation_id))
                if key in seen_request_keys:
                    connection.exec_driver_sql(
                        "UPDATE ai_authorization_requests SET status='expired', "
                        "resolved_at=CURRENT_TIMESTAMP, resolved_by='system:bootstrap', "
                        "claim_token=NULL, claim_expires_at=NULL, updated_at=CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (request_id,),
                    )
                else:
                    seen_request_keys.add(key)
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_authorization_requests_active "
                "ON ai_authorization_requests (actor_id, conversation_id) "
                "WHERE status IN ('pending', 'processing')"
            )
        grant_rows = connection.exec_driver_sql("PRAGMA table_info(ai_authorization_grants)").fetchall()
        if grant_rows:
            connection.exec_driver_sql(
                "UPDATE ai_authorization_grants SET revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE revoked_at IS NULL AND expires_at <= CURRENT_TIMESTAMP"
            )
            connection.exec_driver_sql(
                "UPDATE ai_authorization_grants SET conversation_id=NULL "
                "WHERE revoked_at IS NULL AND scope='remembered'"
            )
            duplicate_grants = connection.exec_driver_sql(
                "SELECT actor_id, conversation_id, scope, id FROM ai_authorization_grants "
                "WHERE revoked_at IS NULL AND scope IN ('conversation', 'remembered') "
                "ORDER BY actor_id, scope, conversation_id, created_at DESC, id DESC"
            ).fetchall()
            seen_grant_keys: set[tuple[str, str, str | None]] = set()
            for actor_id, conversation_id, scope, grant_id in duplicate_grants:
                key = (
                    str(actor_id),
                    str(scope),
                    None if scope == "remembered" else (str(conversation_id) if conversation_id is not None else None),
                )
                if key in seen_grant_keys:
                    connection.exec_driver_sql(
                        "UPDATE ai_authorization_grants SET revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (grant_id,),
                    )
                else:
                    seen_grant_keys.add(key)
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_ai_authorization_grants_actor_scope "
                "ON ai_authorization_grants (actor_id, scope)"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_authorization_grants_conversation_active "
                "ON ai_authorization_grants (actor_id, conversation_id, scope) "
                "WHERE revoked_at IS NULL AND scope = 'conversation'"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_authorization_grants_remembered_active "
                "ON ai_authorization_grants (actor_id, scope) "
                "WHERE revoked_at IS NULL AND scope = 'remembered'"
            )


def _ensure_default_provider_routes() -> None:
    from app.application.ports.provider import PROVIDER_ROUTE_GROUPS

    from .provider_repo_impl import SQLiteProviderRepository

    repo = SQLiteProviderRepository()
    entries = [
        {"provider_account_id": account.id, "model": account.default_model}
        for account in repo.list_configured_openai_providers()
        if account.default_model
    ]
    if not entries:
        return
    for provider_group in PROVIDER_ROUTE_GROUPS:
        if repo.list_routes(provider_group):
            continue
        repo.replace_routes(provider_group, entries)


def _ensure_sqlite_event_delivery_indexes() -> None:
    with engine.begin() as connection:
        delivery_rows = connection.exec_driver_sql("PRAGMA table_info(event_deliveries)").fetchall()
        if delivery_rows:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_event_deliveries_tenant_dedupe_key "
                "ON event_deliveries (tenant_id, dedupe_key)"
            )
        attempt_rows = connection.exec_driver_sql("PRAGMA table_info(event_delivery_attempts)").fetchall()
        if attempt_rows:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_event_delivery_attempts_event_attempt "
                "ON event_delivery_attempts (event_id, attempt_no)"
            )


def bootstrap_sqlite() -> None:
    global _bootstrapped_engine_url

    _ = _schema
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_user_columns()
    _ensure_sqlite_source_columns()
    _ensure_sqlite_job_columns()
    _ensure_sqlite_translation_columns()
    _ensure_sqlite_provider_columns()
    _ensure_sqlite_novel_analysis_columns()
    _ensure_sqlite_ai_conversation_columns()
    _ensure_default_provider_routes()
    _ensure_sqlite_event_delivery_indexes()
    db = SessionLocal()
    try:
        existing = {row.name for row in db.query(PermissionModel).all()}
        for item in build_permission_matrix():
            if item not in existing:
                db.add(PermissionModel(name=item))
        db.flush()

        legacy_role = db.query(RoleModel).filter(RoleModel.name == "super_admin").first()
        if legacy_role is not None and db.query(RoleModel).filter(RoleModel.name == DEFAULT_ROLE_NAME).first() is None:
            legacy_role.name = DEFAULT_ROLE_NAME
            db.flush()
        role = db.query(RoleModel).filter(RoleModel.name == DEFAULT_ROLE_NAME).first()
        if role is None:
            role = RoleModel(name=DEFAULT_ROLE_NAME, description="Built-in full access role")
            db.add(role)
            db.flush()

        linked_ids = {
            row.permission_id
            for row in db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role.id).all()
        }
        for permission in db.query(PermissionModel).all():
            if permission.id not in linked_ids:
                db.add(RolePermissionModel(role_id=role.id, permission_id=permission.id))
        if db.query(RoleModel).filter(RoleModel.name == "user").first() is None:
            db.add(RoleModel(name="user", description="Built-in standard user role"))
        db.commit()
    finally:
        db.close()
    _bootstrapped_engine_url = str(engine.url)


def ensure_sqlite_bootstrap() -> None:
    """Run the full SQLite bootstrap once for the active engine."""
    global _bootstrapped_engine_url

    engine_url = str(engine.url)
    if _bootstrapped_engine_url == engine_url:
        return

    with _bootstrap_lock:
        if _bootstrapped_engine_url == engine_url:
            return
        bootstrap_sqlite()
        _bootstrapped_engine_url = engine_url
