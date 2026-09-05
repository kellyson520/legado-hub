# Low-Memory Docker Public Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a low-memory, persistent Docker Compose deployment for LegadoHub with optional public access through Cloudflare Tunnel and a verified GitHub-ready checkout.

**Architecture:** Build the FastAPI API in a Python slim image and the React UI in a Node builder/Nginx runtime image. Default Compose starts only API and web; Redis, MinIO, and Cloudflare Tunnel are opt-in profiles. SQLite/data/logs remain bind-mounted on the host.

**Tech Stack:** Docker multi-stage builds, Docker Compose, Python 3.11 slim, Node/Vite, Nginx Alpine, Cloudflared.

**Spec:** `docs/design/2026-04-13-docker-public-deployment.md`

## Global Constraints

- Never commit credentials, tokens, databases, logs, `node_modules`, or build caches.
- Default deployment must bind host access to `127.0.0.1`, not expose internal services.
- API defaults to one worker and no reload.
- SQLite, novel files, logs, and backups use host bind mounts.
- Redis and MinIO are optional and never publish host ports by default.
- Cloudflare Tunnel is optional and requires a deployment-provided `CLOUDFLARE_TUNNEL_TOKEN`.
- Do not push until the Git remote is confirmed to be `https://github.com/kellyson520/legado-hub` and authentication is available.

---

### Task 1: Restore and verify complete runtime inputs

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/main.py`
- Create: `.dockerignore`
- Test: existing `backend/tests/`

**Interfaces:**
- Produces: runnable `app.main:app` and complete backend dependency manifest.

- [ ] **Step 1: Restore upstream files**

Fetch the exact files from the target repository without overwriting local feature changes:

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/kellyson520/legado-hub@main/backend/requirements.txt -o backend/requirements.txt
curl -fsSL https://cdn.jsdelivr.net/gh/kellyson520/legado-hub@main/backend/app/main.py -o backend/app/main.py
curl -fsSL https://cdn.jsdelivr.net/gh/kellyson520/legado-hub@main/.dockerignore -o .dockerignore
```

- [ ] **Step 2: Run backend verification**

Run: `cd backend && python3 -m pytest -q && python3 -m compileall -q app tests`
Expected: all tests pass and compileall exits 0.

- [ ] **Step 3: Commit runtime inputs**

```bash
git add backend/requirements.txt backend/app/main.py .dockerignore
git commit -m "chore: restore container runtime inputs"
```

---

### Task 2: Build a minimal API image

**Files:**
- Modify: `backend/Dockerfile`
- Create: `backend/docker-entrypoint.sh`
- Test: `backend/tests/test_deployment_contract.py`

**Interfaces:**
- Produces: image entrypoint `uvicorn app.main:app`, port 8000, non-root runtime.

- [ ] **Step 1: Write deployment contract tests**

```python
def test_dockerfile_uses_non_root_and_single_worker():
    dockerfile = Path("backend/Dockerfile").read_text()
    assert "USER app" in dockerfile
    assert "--workers 1" in dockerfile
    assert "gradle" not in dockerfile.lower()
```

- [ ] **Step 2: Run the contract test and observe RED**

Run: `cd backend && python3 -m pytest tests/test_deployment_contract.py -q`
Expected: FAIL because the current Dockerfile contains Gradle/JVM dependencies and does not declare the app user/single worker.

- [ ] **Step 3: Implement the minimal Dockerfile**

Use a `python:3.11-slim-bookworm` builder to install wheels and a clean `python:3.11-slim-bookworm` runtime. Install only `libxml2`, `libxslt`, and `tini`; create `app` UID 10001; copy installed wheels, application source, and entrypoint; set `USER app`; run `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.

- [ ] **Step 4: Run tests and build the image**

Run:

```bash
cd backend
python3 -m pytest tests/test_deployment_contract.py -q
docker build -t legado-hub-api:local -f Dockerfile ..
```

Expected: contract test passes and image build exits 0.

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile backend/docker-entrypoint.sh backend/tests/test_deployment_contract.py
git commit -m "feat: add slim non-root api image"
```

---

### Task 3: Add static frontend and persistent Compose deployment

**Files:**
- Create: `frontend/Dockerfile`
- Create: `nginx/nginx.conf`
- Create: `docker-compose.yml`
- Create: `docker-compose.override.yml.example`
- Modify: `.env.example`
- Test: `tests/test_compose_contract.py`

**Interfaces:**
- Produces: default services `api` and `web`; optional profiles `redis`, `minio`, `public`; bind mounts `./data`, `./logs`, `./backups`.

- [ ] **Step 1: Write Compose contract tests**

```python
def test_compose_defaults_are_local_and_persistent():
    text = Path("docker-compose.yml").read_text()
    assert "127.0.0.1:8080:80" in text
    assert "./data:/data" in text
    assert "./logs" in text
    assert "mem_limit" in text
    assert "redis" not in text.split("services:", 1)[1].split("profiles:", 1)[0]
```

- [ ] **Step 2: Run RED**

Run: `python3 -m pytest tests/test_compose_contract.py -q`
Expected: FAIL because deployment files do not exist.

- [ ] **Step 3: Implement images and Compose**

Frontend builder installs dependencies and runs `npm run build`; Nginx runtime copies `dist`, uses a read-only config, serves SPA fallback, and proxies `/api/` to `api:8000`.

Compose API mounts `./data:/data`, `./backend/app:/app/app:ro` only in the development override, and `./logs:/app/logs`; web binds `127.0.0.1:8080:80`; Redis and MinIO are profiles with memory limits and no published ports; public profile runs `cloudflare/cloudflared:latest` with `--no-autoupdate tunnel run --token` and only starts when the token is supplied.

- [ ] **Step 4: Validate config**

Run:

```bash
python3 -m pytest tests/test_compose_contract.py -q
docker compose config
DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose --profile public config
```

Expected: all commands exit 0 and rendered config has no host-published Redis/MinIO ports.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.override.yml.example frontend/Dockerfile nginx/nginx.conf .env.example tests/test_compose_contract.py
git commit -m "feat: add persistent low-memory compose deployment"
```

---

### Task 4: Verify images and publish safely

**Files:**
- Modify: `README.md`
- Modify: `docs/design/2026-04-13-docker-public-deployment.md`

**Interfaces:**
- Produces: documented deployment commands and verified local image/service evidence.

- [ ] **Step 1: Build and smoke-test**

Run:

```bash
docker compose build --pull
mkdir -p data logs backups
SECRET_KEY="$(openssl rand -hex 32)" docker compose up -d api web
docker compose ps
docker compose logs --no-color --tail=100 api web
docker compose down
```

Expected: API and web containers become healthy; no service exposes Redis/MinIO ports.

- [ ] **Step 2: Verify public profile safety**

Run: `docker compose --profile public config`
Expected: tunnel config renders but no token value is committed or printed into repository files.

- [ ] **Step 3: Run full project verification**

Run backend pytest/compileall, frontend `npm run test -- --run`, frontend `npm run build`, and `git diff --check`.
Expected: all exit 0.

- [ ] **Step 4: Confirm remote before push**

Run: `git remote -v`
Expected: exact target `https://github.com/kellyson520/legado-hub` with push authentication.

- [ ] **Step 5: Push only after remote confirmation**

```bash
git push origin main
```

Expected: push succeeds. If authentication/network fails, preserve local commits and report the exact error without exposing credentials.

- [ ] **Step 6: Commit documentation and report**

```bash
git add README.md docs/design/2026-04-13-docker-public-deployment.md
git commit -m "docs: document low-memory public deployment"
```
