# LegadoHub Audit Evidence

## 1. Environment Snapshot
| Item | Value |
| --- | --- |
| OS | Windows |
| Working copy | `C:\Users\lihuo\Desktop\legado-hub` |
| Docker used | No |
| Database mode | SQLite audit file |
| Python runtime used for backend | Local Python 3.13 virtualenv (`backend\\.venv`) |
| Follow-up verification date | 2026-07-07 |

## 2. Commands Run
| Step | Command | Exit code | Artifact |
| --- | --- | --- | --- |
| Task 2.1 | `Get-ChildItem -Force 'C:\Users\lihuo\Desktop\legado-hub'` | 0 | Top-level repository inventory |
| Task 2.2 | `Select-String -Path 'README.md','docs/ARCHITECTURE.md','docs/CODE_GUIDE.md' -Pattern 'DDD|v0|v1|auth|translate|websocket|dashboard|router'` | 0 | Documented architecture claims |
| Task 2.3 | `Select-String -Path 'backend/app/main.py' -Pattern 'include_router|from \.interfaces\.api|docs_url|redoc_url|FileResponse|StaticFiles'` | 0 | Backend entry-point surface |
| Task 2.4 | `Get-ChildItem -Depth 2 'backend/app/interfaces/api','backend/app/api','backend/app/routers'` | 0 | Router tree inventory |
| Task 2.5 | `Get-Content` line reads for `frontend/src/api/index.ts`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `backend/app/main.py`, and v0 router prefix files | 0 | Client/server contract references |
| Task 3.1 | `py -3 -m venv .venv` | 0 | Backend virtual environment created with local Python 3.13 |
| Task 3.2 | `python -m pip install -r <temp patched requirements>` + targeted `pip install` commands | Mixed | Dynamic Python 3.13 compatibility install completed after replacing runtime-incompatible pins in the venv only |
| Task 3.3 | `backend\\.venv\\Scripts\\python.exe -c "from app.main import app; print(app.title)"` | 0 | Backend import smoke test |
| Task 3.4 | `Start-Process powershell ... uvicorn app.main:app --host 127.0.0.1 --port 8000` | 0 | Background backend process + `backend-audit.pid` |
| Task 3.5 | `python -m pytest tests\\test_integration.py -k "status or v0_endpoints_do_not_require_auth" -v` | 0 | Backend targeted tests |
| Task 4.1 | `npm install` | 0 | Frontend dependencies installed locally |
| Task 4.2 | `npm run build` | 1 | TypeScript build failed in `vite.config.ts` before Vite bundling |
| Task 4.3 | `npx vite build` | 0 | Direct Vite production bundle succeeded to `frontend/dist` |
| Task 4.4 | `Start-Process powershell ... npm run dev -- --host 127.0.0.1 --port 3000` | 0 | Background frontend dev server + `frontend-audit.pid` |
| Task 5.1 | `Start-Process ... python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` with fresh `audit_legado_hub_task5.db` | 0 | Clean-room backend repro environment for follow-up validation |
| Task 5.2 | `python stdin script: POST -> sqlite check -> GET list/dashboard/output -> DELETE` against `http://127.0.0.1:8000` | 0 | Confirmed direct backend CRUD on fresh DB; earlier "direct list empty" symptom did not reproduce |
| Task 5.3 | `python stdin script: compare snake_case vs camelCase query params on /api/sources/book and /api/output/*` | 0 | Confirmed `pageSize` / `enabledOnly` are ignored while `page_size` / `enabled_only` work |
| Task 5.4 | `python stdin script: create 3 enabled sources then GET /api/dashboard/stats` | 0 | Confirmed dashboard counts are truncated by `page_size=1` logic |
| Task 5.5 | `python stdin script: create grouped source then GET /api/dashboard/groups` | 0 | Confirmed groups endpoint returns `[]` even when grouped data exists |
| Task 5.6 | `Start-Process npm.cmd run dev -- --host 127.0.0.1 --port 3000` | 0 | Frontend repro server for proxy contract checks |
| Task 5.7 | `python stdin script: POST/GET via http://127.0.0.1:3000/api/... using frontend-style params` | 0 | Confirmed Vite proxy forwards camelCase params unchanged, reproducing filter/export drift |
| Task 6.1 | `Get-Content` line reads for `sources.py`, `dashboard.py`, `output.py`, `core/response.py`, `core/security.py`, `core/config.py`, `frontend/src/api/index.ts`, `SourcesPage.tsx`, `ExportPage.tsx`, `SearchTestPage.tsx`, `package.json`, `tsconfig.node.json`, `requirements.txt` | 0 | Exact audit line references |
| Task 6.2 | `npm ls @types/node` | 1 | Confirmed Node typings are not installed in the frontend workspace |
| Task 6.3 | `Get-ChildItem ... | Where-Object { $_.Name -in '.venv','.pytest_cache','htmlcov','dist','node_modules' }` | 0 | Generated/local artifact inventory |

## 3. HTTP Checks
| URL | Method | Result | Evidence |
| --- | --- | --- | --- |
| `http://127.0.0.1:8000/api/status` | GET | PASS | JSON response includes `success=true`, `version=2.1.0`, `storage=sqlite` |
| `http://127.0.0.1:8000/` | GET | FAIL | HTTP 500 with `INTERNAL_ERROR`; backend log shows `RuntimeError: File at path /app/frontend/index.html does not exist.` |
| `http://127.0.0.1:8000/api/sources/book` | POST / GET / DELETE | PASS | Fresh-DB CRUD smoke on 2026-07-07 created, listed, exported, and deleted audit sources without reproducing the earlier empty-list symptom |
| `http://127.0.0.1:8000/api/dashboard/stats` | GET | FAIL | With 3 enabled sources, response returned `bookSources.total=3` but `enabled=1` and `disabled=2`, proving `len(page_size=1)` truncation |
| `http://127.0.0.1:8000/api/dashboard/groups` | GET | FAIL | After creating a source in `bookSourceGroup='audit-group'`, response still returned `{"groups":[]}` |
| `http://127.0.0.1:8000/api/output/book?enabled_only=false` | GET | PASS | Returned both enabled and disabled sources |
| `http://127.0.0.1:8000/api/output/book?enabledOnly=false` | GET | FAIL | Returned only enabled sources because camelCase param was ignored and backend fell back to default `enabled_only=True` |
| `http://127.0.0.1:3000/` | GET | PASS | Vite dev shell returned HTML containing `<div id="root"></div>` |
| `http://127.0.0.1:3000/sources` | GET | PASS | SPA route fallback returned HTML containing `<div id="root"></div>` |
| `http://127.0.0.1:3000/api/status` | GET | PASS | Frontend proxy returned backend status JSON |
| `http://127.0.0.1:3000/api/dashboard/stats` | GET | PASS | Frontend proxy returned backend dashboard JSON, proving transport reachability |
| `http://127.0.0.1:3000/api/sources/book?page=1&pageSize=1&enabledOnly=true` | GET | FAIL | Proxy forwarded frontend-style params unchanged; response came back with `meta.page_size=20`, `total=2`, and both enabled+disabled sources |
| `http://127.0.0.1:3000/api/sources/book?page=1&page_size=1&enabled_only=true` | GET | PASS | Proxy path works when using backend-expected snake_case params, returning only the enabled source and `meta.page_size=1` |
| `http://127.0.0.1:3000/api/output/export.json?enabledOnly=false` | GET | FAIL | Frontend-generated camelCase export link returned only enabled sources |
| `http://127.0.0.1:3000/api/output/export.json?enabled_only=false` | GET | PASS | Snake_case export link returned both enabled and disabled sources |

## 4. File References
| File | Observation | Evidence |
| --- | --- | --- |
| `README.md` + `docs/ARCHITECTURE.md` | Documentation advertises DDD interface layering and both v0 + v1 API surfaces | `README.md:49-50,220-267`; `docs/ARCHITECTURE.md:29-31` |
| `backend/app/main.py` | Only v0 routers are active; v1 imports and `include_router(...)` calls are commented out; `/` serves `/app/frontend/index.html` | `backend/app/main.py:25-27,80-100` |
| `backend/app/interfaces/api/` | DDD-style interface routers exist for both `v0` and `v1` | Router tree inventory captured on 2026-07-06 |
| `backend/app/api/` + `backend/app/routers/` | Parallel legacy router trees still exist beside the interface layer | Router tree inventory captured on 2026-07-06; `docs/CODE_GUIDE.md:90-95` |
| `backend/app/interfaces/api/v0/sources.py` | Source list endpoint expects `page_size` / `enabled_only`; create/delete routes depend only on `get_source_service` | `backend/app/interfaces/api/v0/sources.py:24-59` |
| `backend/app/interfaces/api/v0/output.py` | Output/export endpoints also expect snake_case `enabled_only` | `backend/app/interfaces/api/v0/output.py:19-48` |
| `backend/app/interfaces/api/v0/dashboard.py` | Dashboard stats use `page_size=1` then count `len(items)`; groups endpoint catches missing `list_groups()` and returns `[]` | `backend/app/interfaces/api/v0/dashboard.py:18-66` |
| `backend/app/core/response.py` | Canonical paginated responses put `page`, `page_size`, `total`, and `total_pages` under `meta` | `backend/app/core/response.py:24-29,78-98` |
| `backend/app/core/config.py` + `backend/app/core/security.py` | Default `SECRET_KEY` is hard-coded and password hashing is `SHA256 + SECRET_KEY` rather than bcrypt/argon2 | `backend/app/core/config.py:21-24`; `backend/app/core/security.py:64-73` |
| `backend/app/application/services/auth_service.py` + `backend/requirements.txt` | Auth service stores and verifies passwords through the custom hash even though `passlib[bcrypt]` is declared as a dependency | `backend/app/application/services/auth_service.py:22-44`; `backend/requirements.txt:24-26` |
| `frontend/src/api/index.ts` + `frontend/vite.config.ts` | Frontend uses `baseURL: '/api'`, proxies `/api` to `http://localhost:8000`, sends camelCase params (`pageSize`, `enabledOnly`), and models pagination as top-level `total/page/pageSize` | `frontend/src/api/index.ts:3-5,19-27,60-70,126-133`; `frontend/vite.config.ts:12-18` |
| `frontend/src/pages/SourcesPage.tsx` + `frontend/src/pages/ExportPage.tsx` + `frontend/src/pages/SearchTestPage.tsx` | UI pages consume the drifted contract: `SourcesPage` reads `res.total`, export links use `enabledOnly`, and `SearchTestPage` loads sources with `enabledOnly` then toasts `res.data?.count` | `frontend/src/pages/SourcesPage.tsx:45-55`; `frontend/src/pages/ExportPage.tsx:23-26,42-65`; `frontend/src/pages/SearchTestPage.tsx:39-72` |
| `frontend/src/main.tsx` | SPA routes are client-side and include `/`, `/sources`, `/search`, `/test`, `/health`, and `/export` | `frontend/src/main.tsx:16-27` |
| `backend/tests/test_integration.py` | Test suite explicitly documents that v0 endpoints do not require auth while v1 endpoints should | `backend/tests/test_integration.py:1-12,942-950` |
| `backend/requirements.txt` | Declared pins are not fully runnable on local Python 3.13 without venv-only compatibility overrides, and runtime-needed packages were missing from the file | Install evidence captured on 2026-07-06/07; original pins include `aiohttp==3.9.5` and `sqlalchemy==2.0.30` |
| `backend/app/database.py` + `backend/app/main.py` | Backend can import and serve `/api/status` locally once env vars and compatible packages are present | Import smoke output `LegadoHub Pro`; `backend-audit.log` startup + request trace |
| `frontend/package.json` + `frontend/tsconfig.node.json` | Frontend scripts rely on `tsc -b && vite build`, but the Node-targeted TS config does not include Node typings and `@types/node` is absent from the workspace | `frontend/package.json:6-9,25-30`; `frontend/tsconfig.node.json:1-10`; `npm ls @types/node` on 2026-07-07 |

## 5. Runtime Logs
- Backend log: `docs/superpowers/reports/backend-audit.log`
- Frontend log: `docs/superpowers/reports/frontend-audit.log`
- Backend follow-up stdout log: `docs/superpowers/reports/backend-task5-repro.out.log`
- Backend follow-up stderr log: `docs/superpowers/reports/backend-task5-repro.err.log`
- Frontend follow-up stdout log: `docs/superpowers/reports/frontend-task5-repro.out.log`
- Frontend follow-up stderr log: `docs/superpowers/reports/frontend-task5-repro.err.log`
