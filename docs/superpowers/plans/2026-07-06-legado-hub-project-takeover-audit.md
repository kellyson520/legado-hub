# LegadoHub Project Takeover Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete architecture / engineering / code / security takeover audit for `C:\Users\lihuo\Desktop\legado-hub`, run backend and frontend locally on Windows against an isolated SQLite audit database, and deliver an evidence-backed report plus a candidate-fix list that requires user approval before any code changes.

**Architecture:** Execute the work in four streams: static repository audit, backend local runtime verification, frontend/proxy integration verification, and final evidence-backed reporting. Runtime checks must avoid Docker, prefer shell environment variables over source edits, and isolate state by using a dedicated SQLite audit database file under `backend/data/`.

**Tech Stack:** PowerShell, Python/FastAPI/Uvicorn/Pytest, Node.js/Vite/React, SQLite, HTTP/JSON smoke checks, Markdown documentation

---

## File Structure

### Audit artifacts to create
- `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-candidate-fixes.md`
- `docs/superpowers/reports/backend-audit.log`
- `docs/superpowers/reports/backend-audit.pid`
- `docs/superpowers/reports/frontend-audit.log`
- `docs/superpowers/reports/frontend-audit.pid`
- `backend/data/audit_legado_hub.db`

### Primary reference files
- `docs/superpowers/specs/2026-07-06-legado-hub-project-takeover-audit-design.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/CODE_GUIDE.md`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/src/main.tsx`
- `frontend/src/api/index.ts`
- `backend/requirements.txt`
- `backend/pytest.ini`
- `backend/tests/conftest.py`
- `backend/tests/test_integration.py`
- `backend/app/main.py`
- `backend/app/database.py`
- `backend/app/core/config.py`
- `backend/app/core/redis_client.py`
- `backend/app/core/security.py`
- `backend/app/core/dependencies.py`
- `backend/app/interfaces/api/dependencies.py`
- `backend/app/interfaces/api/v0/dashboard.py`
- `backend/app/interfaces/api/v0/test.py`
- `backend/app/interfaces/api/v1/`
- `backend/app/api/`
- `backend/app/routers/`

---

### Task 1: Create the audit artifact set

**Files:**
- Create: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Create: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Create: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-candidate-fixes.md`
- Create: `docs/superpowers/reports/backend-audit.log`
- Create: `docs/superpowers/reports/frontend-audit.log`
- Reference: `docs/superpowers/specs/2026-07-06-legado-hub-project-takeover-audit-design.md`

- [ ] **Step 1: Create the reports directory**

Run:

```powershell
New-Item -ItemType Directory -Force 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports'
```

Expected: PowerShell prints the created directory or confirms it already exists.

- [ ] **Step 2: Write the audit report skeleton**

```markdown
# LegadoHub Project Takeover Audit Report

> Audit date: 2026-07-06
> Working copy: `C:\Users\lihuo\Desktop\legado-hub`
> Git context: none (`.git` missing in this working copy)

## 1. Executive Summary

## 2. Architecture Audit
| Area | Documented design | Observed implementation | Impact | Evidence |
| --- | --- | --- | --- | --- |

## 3. Engineering Audit
| Check | Result | Evidence | Notes |
| --- | --- | --- | --- |

## 4. Code Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |

## 5. Security Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |

## 6. Candidate Fixes Requiring Approval
| ID | Finding | Proposed change | Approval status |
| --- | --- | --- | --- |

## 7. Recommended Next Actions
```

- [ ] **Step 3: Write the evidence ledger skeleton**

```markdown
# LegadoHub Audit Evidence

## 1. Environment Snapshot
| Item | Value |
| --- | --- |
| OS | Windows |
| Working copy | `C:\Users\lihuo\Desktop\legado-hub` |
| Docker used | No |
| Database mode | SQLite audit file |

## 2. Commands Run
| Step | Command | Exit code | Artifact |
| --- | --- | --- | --- |

## 3. HTTP Checks
| URL | Method | Result | Evidence |
| --- | --- | --- | --- |

## 4. File References
| File | Observation | Evidence |
| --- | --- | --- |

## 5. Runtime Logs
- Backend log: `docs/superpowers/reports/backend-audit.log`
- Frontend log: `docs/superpowers/reports/frontend-audit.log`
```

- [ ] **Step 4: Write the candidate-fix tracker with initial rows**

```markdown
# LegadoHub Candidate Fixes

| ID | Finding | Proposed change | Risk if unchanged | Approval required | Status |
| --- | --- | --- | --- | --- | --- |
| CF-01 | `backend/app/main.py` serves `/app/frontend/index.html` from the root route, which is likely invalid outside the container layout | Decide whether local development should proxy to Vite, serve `frontend/dist`, or return a setup hint | Local root path may fail even when API is healthy | Yes | Pending |
| CF-02 | `backend/app/core/config.py` ships with a hard-coded default `SECRET_KEY` | Require an explicit local/dev secret or generate one at startup for non-production use | Weak default auth/signing boundary | Yes | Pending |
| CF-03 | `backend/app/main.py` allows wildcard CORS (`allow_origins=["*"]`) | Narrow origins for production and document dev-only wildcard usage | Cross-origin exposure is broader than necessary | Yes | Pending |
| CF-04 | `backend/app/main.py` documents v1 API capability but comments out v1 router registration | Either enable the intended surface or downgrade docs to match runtime | Docs/runtime mismatch misleads maintainers and users | Yes | Pending |
| CF-05 | `backend/app/database.py` defaults to `/data/legado_hub.db`, which is Docker-centric | Normalize a Windows/local-friendly default or document the required env override | Local startup can fail or write outside the project unexpectedly | Yes | Pending |
```

- [ ] **Step 5: Verify the artifact set exists**

Run:

```powershell
Get-ChildItem 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports'
```

Expected: the three Markdown files exist; the log files may not exist yet if they have not been created.

---

### Task 2: Perform the static architecture and surface audit

**Files:**
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Reference: `README.md`
- Reference: `docs/ARCHITECTURE.md`
- Reference: `docs/CODE_GUIDE.md`
- Reference: `backend/app/main.py`
- Reference: `backend/app/interfaces/api/`
- Reference: `backend/app/api/`
- Reference: `backend/app/routers/`
- Reference: `frontend/src/main.tsx`
- Reference: `frontend/src/api/index.ts`

- [ ] **Step 1: Capture the top-level repository inventory**

Run:

```powershell
Get-ChildItem -Force 'C:\Users\lihuo\Desktop\legado-hub'
```

Expected: shows `backend`, `frontend`, `docs`, `nginx`, and top-level configuration files.

- [ ] **Step 2: Capture the documented architecture claims**

Run:

```powershell
Select-String -Path 'C:\Users\lihuo\Desktop\legado-hub\README.md','C:\Users\lihuo\Desktop\legado-hub\docs\ARCHITECTURE.md','C:\Users\lihuo\Desktop\legado-hub\docs\CODE_GUIDE.md' -Pattern 'DDD|v0|v1|auth|translate|websocket|dashboard|router' | Select-Object -First 120
```

Expected: prints lines that describe documented layers, API versions, and enabled capabilities.

- [ ] **Step 3: Capture the actual backend entry-point surface**

Run:

```powershell
Select-String -Path 'C:\Users\lihuo\Desktop\legado-hub\backend\app\main.py' -Pattern 'include_router|from \.interfaces\.api|docs_url|redoc_url|FileResponse|StaticFiles'
```

Expected: shows the v0 routers that are actually registered and any commented-out v1 router imports/registrations.

- [ ] **Step 4: Record duplicate or legacy API trees**

Run:

```powershell
Get-ChildItem -Depth 2 'C:\Users\lihuo\Desktop\legado-hub\backend\app\interfaces\api','C:\Users\lihuo\Desktop\legado-hub\backend\app\api','C:\Users\lihuo\Desktop\legado-hub\backend\app\routers' | Select-Object FullName
```

Expected: prints three overlapping API/router trees if they all exist.

- [ ] **Step 5: Write the architecture mismatch table into the audit report**

```markdown
## 2. Architecture Audit
| Area | Documented design | Observed implementation | Impact | Evidence |
| --- | --- | --- | --- | --- |
| API versioning | Docs describe v0 + v1 Pro APIs | `backend/app/main.py` currently registers v0 routers and comments out v1 router registration | Runtime surface is smaller than documentation suggests | `backend/app/main.py` router section |
| DDD layering | Docs present `interfaces -> application -> domain -> infrastructure -> core` | Codebase also contains parallel legacy trees under `app/api` and `app/routers` | Maintainers must determine which tree is authoritative before making changes | directory inventory + router tree listing |
| Frontend contract | Frontend calls `/api/dashboard`, `/api/sources`, `/api/health`, `/api/output`, `/api/test` through a Vite proxy | Backend must expose those paths or the UI will boot but fail at runtime | Broken page-level behavior if the proxy target is incomplete | `frontend/src/api/index.ts` + backend router files |
```

- [ ] **Step 6: Add matching evidence rows to the evidence ledger**

```markdown
## 4. File References
| File | Observation | Evidence |
| --- | --- | --- |
| `backend/app/main.py` | v1 router imports/registrations are commented out | capture the exact commented block and line numbers |
| `backend/app/interfaces/api/` | DDD-style interface routers exist | directory listing |
| `backend/app/api/` + `backend/app/routers/` | legacy/parallel API trees also exist | directory listing |
| `frontend/src/api/index.ts` | frontend assumes `/api` proxy to port 8000 | axios baseURL + endpoint map |
```

---

### Task 3: Prepare and verify the backend local runtime

**Files:**
- Create: `backend/.venv/`
- Create: `backend/data/audit_legado_hub.db`
- Create: `docs/superpowers/reports/backend-audit.log`
- Create: `docs/superpowers/reports/backend-audit.pid`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Reference: `backend/requirements.txt`
- Reference: `backend/app/main.py`
- Reference: `backend/app/database.py`
- Reference: `backend/app/core/config.py`
- Reference: `backend/app/core/redis_client.py`

- [ ] **Step 1: Create a Python virtual environment inside `backend/`**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\backend'
py -3 -m venv .venv
```

Expected: `.venv` is created under `backend/`.

- [ ] **Step 2: Install backend dependencies**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\backend'
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expected: pip finishes successfully and installs FastAPI, SQLAlchemy, redis, pytest, and related packages.

- [ ] **Step 3: Run an import-level smoke test with local audit environment variables**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\backend'
$env:DB_PATH='C:\Users\lihuo\Desktop\legado-hub\backend\data\audit_legado_hub.db'
$env:REPO_BACKEND='sqlite'
$env:DEBUG='true'
$env:SECRET_KEY='audit-local-secret'
$env:REDIS_URL='redis://127.0.0.1:6379/0'
.\.venv\Scripts\python.exe -c "from app.main import app; print(app.title)"
```

Expected: prints `LegadoHub Pro`; if import fails, the traceback becomes the first engineering finding.

- [ ] **Step 4: Start the backend in the background and persist the PID**

Run:

```powershell
$backendRoot='C:\Users\lihuo\Desktop\legado-hub\backend'
$backendLog='C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\backend-audit.log'
$backendPid='C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\backend-audit.pid'
$backendCmd = @"
Set-Location '$backendRoot'
`$env:DB_PATH='C:\Users\lihuo\Desktop\legado-hub\backend\data\audit_legado_hub.db'
`$env:REPO_BACKEND='sqlite'
`$env:DEBUG='true'
`$env:SECRET_KEY='audit-local-secret'
`$env:REDIS_URL='redis://127.0.0.1:6379/0'
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *>> '$backendLog'
"@
$backendProc = Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',$backendCmd -PassThru
Set-Content $backendPid $backendProc.Id
Start-Sleep -Seconds 5
```

Expected: `backend-audit.pid` exists and the backend process is running.

- [ ] **Step 5: Verify the backend status endpoint and root route**

Run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/status'
try {
  Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing | Select-Object -ExpandProperty StatusCode
} catch {
  $_.Exception.Message
}
```

Expected: `/api/status` returns JSON with `version` and `storage`; `/` either returns `200` or reveals the local static-file mismatch that must be documented.

- [ ] **Step 6: Run a targeted backend test subset against the current codebase**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\backend'
$env:DB_PATH='C:\Users\lihuo\Desktop\legado-hub\backend\data\audit_legado_hub.db'
$env:REPO_BACKEND='sqlite'
$env:DEBUG='true'
$env:SECRET_KEY='audit-local-secret'
.\.venv\Scripts\python.exe -m pytest tests\test_integration.py -k "status or v0_endpoints_do_not_require_auth" -v
```

Expected: the selected tests pass; any failures are engineering findings with exact stack traces.

- [ ] **Step 7: Record the backend runtime result in the report and evidence ledger**

Append four concrete rows under `## 3. Engineering Audit` using the exact check names below, the literal observed result (`PASS` or `FAIL`), the exact command or URL from Steps 3-6, and the shortest note that explains what happened:

- `Backend import smoke test`
- `Backend status endpoint`
- `Backend root route`
- `Backend targeted tests`

Also append matching rows under `## 2. Commands Run` and `## 3. HTTP Checks` in `2026-07-06-legado-hub-project-takeover-audit-evidence.md`.

---

### Task 4: Prepare and verify the frontend local runtime

**Files:**
- Create: `docs/superpowers/reports/frontend-audit.log`
- Create: `docs/superpowers/reports/frontend-audit.pid`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Reference: `frontend/package.json`
- Reference: `frontend/vite.config.ts`
- Reference: `frontend/src/main.tsx`
- Reference: `frontend/src/api/index.ts`

- [ ] **Step 1: Install frontend dependencies**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\frontend'
npm install
```

Expected: npm finishes successfully and installs React, Vite, TypeScript, and UI dependencies.

- [ ] **Step 2: Build the frontend once before running the dev server**

Run:

```powershell
Set-Location 'C:\Users\lihuo\Desktop\legado-hub\frontend'
npm run build
```

Expected: Vite completes a production build and writes assets under `frontend/dist`.

- [ ] **Step 3: Start the frontend dev server in the background and persist the PID**

Run:

```powershell
$frontendRoot='C:\Users\lihuo\Desktop\legado-hub\frontend'
$frontendLog='C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\frontend-audit.log'
$frontendPid='C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\frontend-audit.pid'
$frontendCmd = @"
Set-Location '$frontendRoot'
npm run dev -- --host 127.0.0.1 --port 3000 *>> '$frontendLog'
"@
$frontendProc = Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',$frontendCmd -PassThru
Set-Content $frontendPid $frontendProc.Id
Start-Sleep -Seconds 5
```

Expected: `frontend-audit.pid` exists and the Vite server binds to port 3000.

- [ ] **Step 4: Verify the SPA shell on `/` and `/sources`**

Run:

```powershell
(Invoke-WebRequest 'http://127.0.0.1:3000/' -UseBasicParsing).Content | Select-String 'id="root"'
(Invoke-WebRequest 'http://127.0.0.1:3000/sources' -UseBasicParsing).Content | Select-String 'id="root"'
```

Expected: both responses include the root mount node and confirm the client router is reachable.

- [ ] **Step 5: Verify the frontend proxy reaches the backend**

Run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:3000/api/status'
Invoke-RestMethod 'http://127.0.0.1:3000/api/dashboard/stats'
```

Expected: the proxy returns backend JSON; if `/api/dashboard/stats` fails, document whether the failure is a backend route issue, data issue, or proxy issue.

- [ ] **Step 6: Record the frontend runtime result in the report and evidence ledger**

Append four concrete rows under `## 3. Engineering Audit` using the exact check names below, the literal observed result (`PASS` or `FAIL`), the exact command or URL from Steps 1-5, and a short explanatory note:

- `Frontend dependency install`
- `Frontend production build`
- `Frontend dev server`
- `Frontend proxy to backend`

Also append matching rows under `## 2. Commands Run` and `## 3. HTTP Checks` in `2026-07-06-legado-hub-project-takeover-audit-evidence.md`.

---

### Task 5: Run end-to-end API and data-flow smoke checks against the isolated SQLite audit DB

**Files:**
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Reference: `backend/app/interfaces/api/v0/dashboard.py`
- Reference: `backend/app/interfaces/api/v0/test.py`
- Reference: `frontend/src/api/index.ts`
- Runtime target: `backend/data/audit_legado_hub.db`

- [ ] **Step 1: Seed the isolated audit database with a minimal book source via the backend API**

Run:

```powershell
$body = @{
  bookSourceUrl = 'https://audit-source.example/book'
  bookSourceName = 'Audit Source'
  bookSourceGroup = 'audit'
  enabled = $true
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/sources/book' -ContentType 'application/json' -Body $body
```

Expected: returns `success = true` and echoes the created source.

- [ ] **Step 2: Verify the source list from the backend and from the Vite proxy**

Run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/sources/book?page=1&page_size=20'
Invoke-RestMethod 'http://127.0.0.1:3000/api/sources/book?page=1&page_size=20'
```

Expected: both responses include the seeded `Audit Source` record.

- [ ] **Step 3: Verify dashboard and output endpoints against the seeded dataset**

Run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/dashboard/stats'
Invoke-RestMethod 'http://127.0.0.1:8000/api/output/book?enabledOnly=true'
```

Expected: dashboard totals reflect at least one source and output endpoints return Legado-compatible JSON.

- [ ] **Step 4: Verify the audit database file was created where expected**

Run:

```powershell
Get-Item 'C:\Users\lihuo\Desktop\legado-hub\backend\data\audit_legado_hub.db'
```

Expected: the SQLite file exists under `backend/data/`.

- [ ] **Step 5: Delete the seeded record to leave the isolated audit DB clean**

Run:

```powershell
Invoke-RestMethod -Method Delete -Uri 'http://127.0.0.1:8000/api/sources/book/https://audit-source.example/book'
```

Expected: returns `success = true`.

- [ ] **Step 6: Record the smoke-check results in the report and evidence ledger**

Append four concrete rows under `## 3. Engineering Audit` using the exact check names below, the literal observed result (`PASS` or `FAIL`), the exact endpoint from Steps 1-5, and a one-line note that explains the observed behavior:

- `Backend CRUD smoke check`
- `Dashboard data path`
- `Output/export path`
- `Frontend proxy CRUD path`

Also append matching rows under `## 3. HTTP Checks` in `2026-07-06-legado-hub-project-takeover-audit-evidence.md`.

---

### Task 6: Complete the code-quality and security review

**Files:**
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-candidate-fixes.md`
- Reference: `backend/app/main.py`
- Reference: `backend/app/core/config.py`
- Reference: `backend/app/core/security.py`
- Reference: `backend/app/core/dependencies.py`
- Reference: `backend/app/interfaces/api/dependencies.py`
- Reference: `backend/app/api/`
- Reference: `backend/app/routers/`
- Reference: `backend/app/interfaces/api/`
- Reference: `frontend/src/api/index.ts`

- [ ] **Step 1: Search for security-sensitive defaults and broad exposure settings**

Run:

```powershell
Select-String -Path 'C:\Users\lihuo\Desktop\legado-hub\backend\app\main.py','C:\Users\lihuo\Desktop\legado-hub\backend\app\core\config.py','C:\Users\lihuo\Desktop\legado-hub\backend\app\core\security.py' -Pattern 'SECRET_KEY|allow_origins|docs_url|redoc_url|Authorization|Bearer|DEBUG'
```

Expected: returns the exact lines that define the current security posture.

- [ ] **Step 2: Search for runtime/documentation mismatch indicators and dormant surfaces**

Run:

```powershell
Select-String -Path 'C:\Users\lihuo\Desktop\legado-hub\backend\app\main.py','C:\Users\lihuo\Desktop\legado-hub\backend\app\interfaces\api\v1\*.py','C:\Users\lihuo\Desktop\legado-hub\backend\app\api\**\*.py','C:\Users\lihuo\Desktop\legado-hub\backend\app\routers\*.py' -Pattern 'include_router|APIRouter|@router|TODO|FIXME' -ErrorAction SilentlyContinue
```

Expected: prints router registrations, commented surfaces, and any inline maintenance markers.

- [ ] **Step 3: Search for stale generated artifacts and duplicate code trees**

Run:

```powershell
Get-ChildItem -Recurse -Directory 'C:\Users\lihuo\Desktop\legado-hub\backend','C:\Users\lihuo\Desktop\legado-hub\frontend' | Where-Object { $_.Name -in '__pycache__','dist','.pytest_cache','htmlcov' } | Select-Object FullName
```

Expected: lists local/generated artifacts that may affect takeover clarity and review hygiene.

- [ ] **Step 4: Write the code-audit and security-audit severity tables**

```markdown
## 4. Code Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |
| Parallel API trees (`interfaces/api`, `api`, `routers`) create ambiguity | High | directory listing + router imports | New work can land in the wrong layer and diverge further |
| Root route depends on container path layout | High | `backend/app/main.py` + `GET /` result | Local development behavior differs from docs/runtime expectations |
| Docker-centric DB default path leaks into local startup behavior | Medium | `backend/app/database.py` | Local runs require an env override that is not self-evident |

## 5. Security Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |
| Hard-coded default `SECRET_KEY` | High | `backend/app/core/config.py` | Weakens JWT or token signing assumptions |
| Wildcard CORS | Medium | `backend/app/main.py` | Overexposes the API surface to arbitrary origins |
| Documented v1 auth surface not enabled in runtime | Medium | docs + router registration mismatch | Security claims and live enforcement can diverge |
```

- [ ] **Step 5: Update the candidate-fix tracker with confirmed evidence and approval notes**

Update rows `CF-01` through `CF-05` in `2026-07-06-legado-hub-project-takeover-candidate-fixes.md` using this rule set:

- If the evidence confirms the concern, keep the row and replace the finding text with a concise confirmed statement plus an exact file reference.
- If the evidence disproves the concern, change `Status` to `Ruled out by evidence` and explain why in the `Finding` column.
- If the concern is confirmed and still needs user permission before edits, set `Status` to `Awaiting user approval`.
- Replace any generic proposal text with the exact recommended change you would ask the user to approve.

---

### Task 7: Finalize the audit package and shut down local services

**Files:**
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-report.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-audit-evidence.md`
- Modify: `docs/superpowers/reports/2026-07-06-legado-hub-project-takeover-candidate-fixes.md`
- Modify: `docs/superpowers/reports/backend-audit.pid`
- Modify: `docs/superpowers/reports/frontend-audit.pid`

- [ ] **Step 1: Fill the executive summary with evidence-backed pass/fail statements**

Write four final bullets under `## 1. Executive Summary`:

- `Backend local status: PASS ...` or `Backend local status: FAIL ...`
- `Frontend local status: PASS ...` or `Frontend local status: FAIL ...`
- `End-to-end local status: PASS ...` or `End-to-end local status: FAIL ...`
- `Highest-risk finding: <severity> - <one-sentence finding with exact file reference>`

- [ ] **Step 2: Fill the final next-action list in priority order**

Write exactly three ordered actions under `## 7. Recommended Next Actions`, using the highest-priority concrete items that emerged from Tasks 2-6. The final list must contain:

1. The top runtime or startup blocker.
2. The top architecture or docs/runtime alignment issue.
3. The top approved-or-awaiting-approval security/configuration issue.

- [ ] **Step 3: Cross-check the report, evidence ledger, and candidate-fix tracker for consistency**

Run:

```powershell
Select-String -Path 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\2026-07-06-legado-hub-project-takeover-audit-report.md','C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\2026-07-06-legado-hub-project-takeover-audit-evidence.md','C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\2026-07-06-legado-hub-project-takeover-candidate-fixes.md' -Pattern 'Pass / Fail|Pending user review|High|Medium|Low'
```

Expected: returns matching entries so you can confirm every severity and fix appears in the right file.

- [ ] **Step 4: Stop the backend and frontend background processes using the PID files**

Run:

```powershell
if (Test-Path 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\backend-audit.pid') {
  $backendPid = Get-Content 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\backend-audit.pid'
  if ($backendPid) { Stop-Process -Id $backendPid -ErrorAction SilentlyContinue }
}
if (Test-Path 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\frontend-audit.pid') {
  $frontendPid = Get-Content 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports\frontend-audit.pid'
  if ($frontendPid) { Stop-Process -Id $frontendPid -ErrorAction SilentlyContinue }
}
```

Expected: both local servers are stopped and ports 8000 / 3000 are released.

- [ ] **Step 5: Verify that the final deliverables exist and are ready for review**

Run:

```powershell
Get-ChildItem 'C:\Users\lihuo\Desktop\legado-hub\docs\superpowers\reports'
```

Expected: the report, evidence ledger, candidate-fix tracker, log files, and PID files are present.
