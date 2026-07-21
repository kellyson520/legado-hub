from app.core.permissions import DEFAULT_ROLE_NAME, build_permission_matrix
from app.database import Base, SessionLocal, engine

from . import schema as _schema
from .schema import PermissionModel, RoleModel, RolePermissionModel


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


def _ensure_sqlite_novel_columns() -> None:
    """Add Task 1 novel ownership/context columns to existing databases."""
    required = {
        "ai_conversations": {
            "owner_scope": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "book_id": "INTEGER",
            "entrypoint": "VARCHAR NOT NULL DEFAULT 'workspace'",
            "context_range": "VARCHAR NOT NULL DEFAULT 'book'",
            "model_ref": "VARCHAR",
            "knowledge_version": "VARCHAR NOT NULL DEFAULT ''",
            "toolset_version": "VARCHAR NOT NULL DEFAULT ''",
        },
        "ai_conversation_messages": {
            "owner_scope": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "entrypoint": "VARCHAR NOT NULL DEFAULT 'workspace'",
            "book_id": "INTEGER",
            "chapter_id": "INTEGER",
        },
        "novel_ingestions": {
            "owner_scope": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "book_id": "INTEGER",
        },
        "novel_tasks": {
            "owner_scope": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "book_id": "INTEGER",
            "chapter_id": "INTEGER",
        },
    }
    with engine.begin() as connection:
        for table, columns in required.items():
            rows = connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                continue
            existing = {row[1] for row in rows}
            for column, ddl in columns.items():
                if column not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _ensure_sqlite_novel_vector_table() -> None:
    """Create the local vector table for databases created before Task 4."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE IF NOT EXISTS novel_vectors (
                owner_scope VARCHAR NOT NULL,
                book_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                knowledge_version VARCHAR NOT NULL,
                vector TEXT NOT NULL DEFAULT '[]',
                payload TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(owner_scope, book_id, chapter_id, knowledge_version)
            )"""
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version "
            "ON novel_vectors(owner_scope, book_id, knowledge_version)"
        )


def _ensure_sqlite_agent_runtime_columns() -> None:
    """Add request-level novel audit metadata to existing agent run tables."""
    required_columns = {
        "owner_scope": "VARCHAR NOT NULL DEFAULT 'legacy'",
        "book_id": "INTEGER",
        "chapter_id": "INTEGER",
        "entrypoint": "VARCHAR NOT NULL DEFAULT ''",
        "conversation_id": "VARCHAR NOT NULL DEFAULT ''",
        "provider_name": "VARCHAR NOT NULL DEFAULT ''",
        "model_name": "VARCHAR NOT NULL DEFAULT ''",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "cache_hit": "BOOLEAN NOT NULL DEFAULT 0",
        "input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cost": "FLOAT NOT NULL DEFAULT 0",
        "tool_names": "TEXT NOT NULL DEFAULT '[]'",
        "evidence_ids": "TEXT NOT NULL DEFAULT '[]'",
    }
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(agent_runs)").fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}
        for column, ddl in required_columns.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE agent_runs ADD COLUMN {column} {ddl}")
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_tenant_created "
            "ON agent_runs(tenant_id, created_at DESC)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_owner_book "
            "ON agent_runs(owner_scope, book_id, created_at DESC)"
        )


def _ensure_default_provider_routes() -> None:
    from .provider_repo_impl import SQLiteProviderRepository

    repo = SQLiteProviderRepository()
    entries = [
        {"provider_account_id": account.id, "model": account.default_model}
        for account in repo.list_configured_openai_providers()
        if account.default_model
    ]
    if not entries:
        return
    existing_routes = repo.has_routes()
    provider_groups = (
        ("novel_chat", "novel_extract", "novel_summary", "novel_embedding")
        if existing_routes
        else (
            "default", "ai", "source_build", "translation", "novel",
            "novel_chat", "novel_extract", "novel_summary", "novel_embedding",
        )
    )
    for provider_group in provider_groups:
        if not repo.list_routes(provider_group):
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
    _ = _schema
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_user_columns()
    _ensure_sqlite_source_columns()
    _ensure_sqlite_job_columns()
    _ensure_sqlite_translation_columns()
    _ensure_sqlite_provider_columns()
    _ensure_sqlite_novel_columns()
    _ensure_sqlite_novel_vector_table()
    _ensure_sqlite_agent_runtime_columns()
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
