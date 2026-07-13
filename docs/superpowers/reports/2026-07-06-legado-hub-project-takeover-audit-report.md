# LegadoHub Project Takeover Audit Report

> Audit date: 2026-07-06
> Follow-up verification: 2026-07-07
> Working copy: `C:\Users\lihuo\Desktop\legado-hub`
> Git context: none (`.git` missing in this working copy)

## 1. Executive Summary
- LegadoHub can be started locally on Windows with local Python 3.13 + SQLite, but the backend is not turnkey: `backend/requirements.txt` is not directly runnable on Python 3.13, and local startup required venv-only compatibility overrides plus manual installation of missing runtime dependencies.
- The main takeover blocker is contract drift rather than one isolated runtime exception. Documentation still advertises v1/auth surfaces, runtime only registers v0 routers, backend `/` serves a container-only frontend path, and the frontend request/response contract no longer matches the backend query/response shape.
- The earlier "direct list empty but dashboard/output visible" symptom did not reproduce on a fresh audit DB. The confirmed user-facing defects are broader: frontend camelCase query params (`pageSize`, `enabledOnly`) are ignored by FastAPI endpoints that expect snake_case, `SourcesPage` reads `res.total` while the backend returns `meta.total`, dashboard stats cap enabled/error counts at 1, and `/api/dashboard/groups` always returns `[]`.
- Security posture is not production-ready: v0 source mutation/import routes are unauthenticated, `SECRET_KEY` has a hard-coded default, password hashing is a custom `SHA256 + SECRET_KEY` scheme despite `passlib[bcrypt]` being declared, and CORS is wildcard with credentials enabled.

## 2. Architecture Audit
| Area | Documented design | Observed implementation | Impact | Evidence |
| --- | --- | --- | --- | --- |
| API versioning | `README.md` advertises both v0 compatibility APIs and v1 Pro APIs such as `auth`, `ai`, `websocket`, and `translate` | `backend/app/main.py` imports and registers only v0 routers; v1 imports and `include_router(...)` calls are commented out | Runtime surface is smaller than the documentation suggests, which raises takeover and support risk | `README.md:49-50,220-267`; `backend/app/main.py:25-27,80-93` |
| Router/layer authority | Docs describe `app/interfaces/api/v0` and `app/interfaces/api/v1` as the DDD interface layer, while also noting legacy compatibility trees | The working copy still contains three overlapping router trees: `app/interfaces/api`, `app/api/routers`, and `app/routers` | Maintainers must decide which tree is authoritative before making changes, or drift will continue | `docs/ARCHITECTURE.md:29-31`; `docs/CODE_GUIDE.md:77-95`; router tree inventory captured on 2026-07-06 |
| Frontend-to-backend contract | Frontend dev runtime uses `baseURL: '/api'`, a Vite proxy to `http://localhost:8000`, and client-side routes for `/`, `/sources`, `/search`, `/test`, `/health`, `/export` | Backend v0 routers expose matching `/api/dashboard`, `/api/sources`, `/api/health`, `/api/output`, and `/api/test` prefixes, but backend `/` serves `FileResponse('/app/frontend/index.html')` instead of the local SPA shell | API families look aligned for proxied dev traffic, but backend root delivery diverges from the frontend's local runtime model | `frontend/vite.config.ts:12-18`; `frontend/src/api/index.ts:3-5,30-133`; `frontend/src/main.tsx:16-27`; `backend/app/main.py:98-100`; `backend/app/interfaces/api/v0/sources.py:20`; `backend/app/interfaces/api/v0/health.py:14`; `backend/app/interfaces/api/v0/output.py:18`; `backend/app/interfaces/api/v0/dashboard.py:15`; `backend/app/interfaces/api/v0/test.py:16` |

## 3. Engineering Audit
| Check | Result | Evidence | Notes |
| --- | --- | --- | --- |
| Backend import smoke test | PASS | `backend\\.venv\\Scripts\\python.exe -c "from app.main import app; print(app.title)"` | Passed under local Python 3.13 after dynamic compatibility installs in the venv (`aiohttp 3.14.1`, `lxml 6.1.1`, `sqlalchemy 2.0.51`, `jsonpath-ng`, `ply`) |
| Backend status endpoint | PASS | `GET http://127.0.0.1:8000/api/status` | Returned `success=true`, `version=2.1.0`, `storage=sqlite` |
| Backend root route | FAIL | `GET http://127.0.0.1:8000/` | Returned HTTP 500 because `FileResponse('/app/frontend/index.html')` points to a container-only path |
| Backend targeted tests | PASS | `python -m pytest tests\\test_integration.py -k "status or v0_endpoints_do_not_require_auth" -v` | 5 selected tests passed on 2026-07-06 |
| Frontend dependency install | PASS | `npm install` | Completed successfully; npm reported 2 known vulnerabilities in dependency tree |
| Frontend production build | FAIL | `npm run build` | TypeScript phase failed because `vite.config.ts` could not resolve Node `path` / `__dirname`; direct `npx vite build` still succeeds |
| Frontend dev server | PASS | `npm run dev -- --host 127.0.0.1 --port 3000` | Vite dev server bound to `http://127.0.0.1:3000/` |
| Frontend proxy reachability | PASS | `GET http://127.0.0.1:3000/api/status`; `GET http://127.0.0.1:3000/api/dashboard/stats` | Vite proxy can reach the backend process locally |
| Backend CRUD smoke check | PASS | `POST/GET/DELETE http://127.0.0.1:8000/api/sources/book` against fresh `audit_legado_hub_task5.db` | On a fresh audit DB the direct backend path created, listed, exported, and deleted sources correctly; the previously observed "direct list empty" symptom did not reproduce |
| Dashboard data path | FAIL | `GET http://127.0.0.1:8000/api/dashboard/stats`; `GET http://127.0.0.1:8000/api/dashboard/groups` | `dashboard.py` uses `page_size=1` and then counts `len(items)`, so enabled/error counts cap at 1; `groups` always falls back to `[]` because `SourceAppService` has no `list_groups()` implementation |
| Output/export path | FAIL | `GET http://127.0.0.1:8000/api/output/book?enabled_only=false`; `GET http://127.0.0.1:8000/api/output/book?enabledOnly=false`; `GET http://127.0.0.1:8000/api/output/export.json?...` | Backend export works for snake_case params, but camelCase `enabledOnly=false` is ignored and silently falls back to the default `enabled_only=True` behavior |
| Frontend proxy CRUD path | FAIL | `GET http://127.0.0.1:3000/api/sources/book?page=1&pageSize=1&enabledOnly=true`; `GET http://127.0.0.1:3000/api/output/export.json?enabledOnly=false` | The proxy forwards frontend-style camelCase params unchanged, so pagination/filter/export behavior diverges from what the UI intends |

## 4. Code Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |
| Frontend and backend API contracts have drifted apart | High | `frontend/src/api/index.ts:19-27,60-70,126-133`; `frontend/src/pages/SourcesPage.tsx:45-55`; `frontend/src/pages/ExportPage.tsx:23-26,42-65`; `frontend/src/pages/SearchTestPage.tsx:39-72`; `backend/app/core/response.py:24-29,78-98`; `backend/app/interfaces/api/v0/sources.py:25-42`; `backend/app/interfaces/api/v0/output.py:19-48` | The frontend sends `pageSize` / `enabledOnly` and expects top-level `total/page/pageSize`, while the backend reads `page_size` / `enabled_only` and returns pagination inside `meta`. This deterministically breaks filtering, pagination, export toggles, and some UI counters |
| Dashboard statistics and groups endpoints are logically incorrect | High | `backend/app/interfaces/api/v0/dashboard.py:18-66`; HTTP checks on 2026-07-07 with 3 enabled sources and a populated `bookSourceGroup` | `enabled`, `disabled`, `ok`, and `error` counts are derived from one-page slices (`page_size=1`) rather than totals, and the groups endpoint swallows a missing service method by returning `[]` |
| Local Python 3.13 setup is not reproducible from the declared backend requirements | High | `backend/requirements.txt:1-29`; follow-up environment notes in evidence | The working copy only ran after venv-only compatibility overrides (`aiohttp`, `lxml`, `sqlalchemy`) and manual installation of missing runtime deps (`jsonpath-ng`, `ply`), so takeover is fragile and undocumented |
| Frontend build pipeline is misconfigured for Node-aware TypeScript config files | Medium | `frontend/package.json:6-9,25-30`; `frontend/tsconfig.node.json:1-10`; `npm run build` failure; `npm ls @types/node` returned empty | `npm run build` is the advertised production build entrypoint, but it currently fails before bundling because `vite.config.ts` lacks Node typings / config support |
| The working copy contains generated/local environment artifacts | Low | `backend/.venv`; `backend/.pytest_cache`; `backend/htmlcov`; `frontend/dist`; `frontend/node_modules` | These directories are expected during local work, but they make takeover diffing and provenance review noisier when the working copy is already outside git |

## 5. Security Audit
| Finding | Severity | Evidence | Why it matters |
| --- | --- | --- | --- |
| v0 source mutation and import routes are unauthenticated | High | `backend/app/interfaces/api/v0/sources.py:24-59`; `backend/app/main.py:79-93`; `backend/tests/test_integration.py:1-12,942-950`; unauthenticated `POST` / `DELETE` runtime checks on 2026-07-07 | Any reachable v0 deployment can create, update, import, and delete source data without `Authorization` headers because only service dependencies are injected and the intended v1 auth surface is not registered |
| `SECRET_KEY` has a hard-coded default and is reused for JWT signing and password hashing | High | `backend/app/core/config.py:21-24`; `backend/app/core/security.py:33-45,64-73` | If operators forget to override the default, JWT trust and password hashing both collapse onto a known static secret |
| Password hashing is a custom `SHA256 + SECRET_KEY` scheme instead of an adaptive password hash | High | `backend/app/core/security.py:64-73`; `backend/app/application/services/auth_service.py:22-44`; `backend/requirements.txt:24-26` | The code declares `passlib[bcrypt]` but does not use it. Fast SHA256-based hashing is substantially weaker than bcrypt/argon2 for stored administrator credentials |
| CORS is wildcard with credentials enabled | Medium | `backend/app/core/config.py:55-56`; `backend/app/main.py:69-75` | This keeps the browser-origin trust boundary broader than necessary and does not reflect a least-privilege production posture |

## 6. Candidate Fixes Requiring Approval
| ID | Finding | Proposed change | Approval status |
| --- | --- | --- | --- |
| CF-01 | Backend `/` uses a container-only frontend path | Replace `FileResponse('/app/frontend/index.html')` with an explicit local-dev strategy: serve `frontend/dist`, proxy to Vite, or return a setup hint when no built SPA is present | Awaiting approval |
| CF-02 | Default `SECRET_KEY` is hard-coded | Require an explicit secret in non-test environments or generate a per-instance dev secret at startup | Awaiting approval |
| CF-03 | CORS is wildcard with credentials | Route CORS through `settings.CORS_ORIGINS` and ship restrictive defaults outside local development | Awaiting approval |
| CF-04 | Docs/runtime API surface mismatch | Either enable the intended v1 routers or downgrade docs/tests/UI copy so runtime and documentation describe the same surface | Awaiting approval |
| CF-05 | Local DB/runtime packaging is not reproducible on Python 3.13 | Normalize supported versions and dependency pins, add the missing runtime packages, and replace the Docker-centric default DB path with a documented local-friendly behavior | Awaiting approval |
| CF-06 | Frontend/back-end API contract drift breaks pagination/filter/export | Standardize query parameter casing and response envelopes, then update all affected frontend pages to read the canonical shape | Awaiting approval |
| CF-07 | Dashboard stats/groups logic is incorrect | Use repository totals instead of `len(page_size=1)` slices and implement a real `list_groups()` path instead of silent fallback | Awaiting approval |
| CF-08 | Auth hardening is incomplete | Decide whether v0 writes must require auth, then gate them accordingly and replace custom password hashing with bcrypt/argon2-backed storage | Awaiting approval |

## 7. Recommended Next Actions
1. Freeze the authoritative API surface before any feature work: decide whether `interfaces/api/v0` remains the compatibility layer or whether v1/auth should become active, then align docs, frontend client code, and backend response/query conventions in one pass.
2. Harden the security baseline before any non-local exposure: require non-default secrets, replace password hashing with bcrypt/argon2, decide how v0 write endpoints should be authenticated, and narrow CORS to explicit origins.
3. Make local development reproducible: publish the supported Python/Node matrix, fix `backend/requirements.txt` for Python 3.13, repair `npm run build`, and remove container-only path assumptions from the backend root route and DB defaults.
