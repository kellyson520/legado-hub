# Cache SQLite Bootstrap in Service Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent repeated SQLite schema/migration/bootstrap work during normal service construction while preserving explicit `bootstrap_sqlite()` calls for migrations and tests.

**Architecture:** Keep `bootstrap_sqlite()` as the explicit full initialization operation. Add a lock-protected `ensure_sqlite_bootstrap()` wrapper keyed by the active SQLAlchemy engine URL; it runs the full operation once per process/database key and retries if initialization fails. All persistence factory builders use the cached wrapper, so request paths no longer repeat schema and permission setup.

**Tech Stack:** Python 3.12, SQLAlchemy, SQLite, pytest.

---

### Task 1: Add a failing cache-contract test

**Files:**
- Modify: `backend/tests/test_runtime_bootstrap.py`

- [ ] **Step 1: Add a test for once-per-engine initialization**

Append:

```python
def test_cached_sqlite_bootstrap_runs_once_per_engine(monkeypatch):
    from app.infrastructure.persistence.sqlite import bootstrap as bootstrap_module

    calls = 0

    def fake_bootstrap():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(bootstrap_module, 'bootstrap_sqlite', fake_bootstrap)
    monkeypatch.setattr(bootstrap_module, '_bootstrapped_engine_url', None)

    bootstrap_module.ensure_sqlite_bootstrap()
    bootstrap_module.ensure_sqlite_bootstrap()

    assert calls == 1
```

This test isolates the cache wrapper and does not modify the production database.

- [ ] **Step 2: Run the test before implementation**

```bash
/root/.venvs/legado-hub/bin/pytest -q tests/test_runtime_bootstrap.py::test_cached_sqlite_bootstrap_runs_once_per_engine
```

Expected: FAIL because `ensure_sqlite_bootstrap` and its cache do not exist yet.

### Task 2: Implement the lock-protected cached wrapper

**Files:**
- Modify: `backend/app/infrastructure/persistence/sqlite/bootstrap.py:1-160`

- [ ] **Step 1: Add cache state and a lock**

Add:

```python
from threading import Lock

_bootstrap_lock = Lock()
_bootstrapped_engine_url: str | None = None
```

- [ ] **Step 2: Add the cached entry point after `bootstrap_sqlite()`**

Add:

```python
def ensure_sqlite_bootstrap() -> None:
    global _bootstrapped_engine_url

    engine_url = str(engine.url)
    if _bootstrapped_engine_url == engine_url:
        return

    with _bootstrap_lock:
        if _bootstrapped_engine_url == engine_url:
            return
        bootstrap_sqlite()
        _bootstrapped_engine_url = engine_url
```

Do not alter the body or behavior of `bootstrap_sqlite()`; if it raises, the cache key must remain unset so a later call retries.

- [ ] **Step 3: Run the cache test**

```bash
/root/.venvs/legado-hub/bin/pytest -q tests/test_runtime_bootstrap.py::test_cached_sqlite_bootstrap_runs_once_per_engine
```

Expected: PASS.

### Task 3: Migrate all persistence factory builders

**Files:**
- Modify: `backend/app/infrastructure/persistence/factory.py:1-500`

- [ ] **Step 1: Import the cached wrapper**

Replace the bootstrap import with:

```python
from app.infrastructure.persistence.sqlite.bootstrap import ensure_sqlite_bootstrap
```

- [ ] **Step 2: Replace every factory bootstrap call**

Replace all 21 exact calls:

```python
bootstrap_sqlite()
```

with:

```python
ensure_sqlite_bootstrap()
```

Do not change builder return types, repository wiring, singleton behavior, or compatibility aliases.

- [ ] **Step 3: Verify no factory uses the uncached entry point**

```bash
rg -n "bootstrap_sqlite|ensure_sqlite_bootstrap" backend/app/infrastructure/persistence/factory.py
```

Expected: only the import and `ensure_sqlite_bootstrap()` calls remain; no direct `bootstrap_sqlite()` calls.

### Task 4: Run backend verification and commit

**Files:**
- No additional source files.

- [ ] **Step 1: Run bootstrap and factory regression tests**

```bash
/root/.venvs/legado-hub/bin/pytest -q \
  tests/test_runtime_bootstrap.py \
  tests/test_provider_registry.py \
  tests/test_api_health.py \
  tests/test_api_provider_platform.py::test_provider_management_lists_and_updates_accounts
```

Expected: all selected tests pass, including the provider-route scenario that explicitly calls full `bootstrap_sqlite()` twice.

- [ ] **Step 2: Compile the backend**

```bash
/root/.venvs/legado-hub/bin/python -m compileall -q app
```

Expected: exit code 0.

- [ ] **Step 3: Check, review, and commit**

```bash
git diff --check
git status --short
git add backend/app/infrastructure/persistence/sqlite/bootstrap.py backend/app/infrastructure/persistence/factory.py backend/tests/test_runtime_bootstrap.py docs/superpowers/plans/2026-07-17-cache-sqlite-bootstrap.md
git commit -m "perf: cache sqlite bootstrap in factories"
```

Expected: one focused commit that preserves explicit bootstrap behavior while removing repeated factory initialization.
