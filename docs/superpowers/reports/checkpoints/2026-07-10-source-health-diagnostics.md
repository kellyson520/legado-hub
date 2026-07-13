# 2026-07-10 Source Health Diagnostics Checkpoint

## Verification

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_source_health_classifier_service.py tests\test_source_probe_service.py tests\test_source_health_admin_service.py tests\test_source_health_repo.py tests\test_source_routing_service.py tests\test_api_source_health.py -q
```

Result: `17 passed`.

```powershell
cd frontend
npm test -- --run src/features/sources/SourceHealthPage.test.tsx src/features/sources/SourceHealthDetailPage.test.tsx
npm run build
```

Result: `2 passed`; TypeScript and Vite production build completed.

## Real-source Results

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\probe_source_health.py --source-ids 30 67 108 --keywords 捞尸人 斗罗大陆 --probe-mode full_chain
```

| Source ID | Health | Search / TOC / Content | Classification | Route policy | Evidence summary |
| --- | --- | --- | --- | --- | --- |
| 30 | `blocked` | `failed / skipped / skipped` | `network_unreachable` | `skip` | Search transport status `0`; no parser result was produced. |
| 67 | `blocked` | `failed / skipped / skipped` | `waf_blocked` | `skip` | Search returned HTTP `403` and HTML challenge content. |
| 108 | `blocked` | `ok / failed / skipped` | `auth_required` | `skip` | Search succeeded; TOC returned HTTP `200` JSON with `meta.status=4200` (logged-out/private response), then parsed empty. |

All results were persisted through `source_probe_runs` and are available through the single-source health detail API and `/sources/health/:sourceId`.

## Residual unknown_error Cases

None of the requested sources remained `unknown_error`. Other sources may still receive `unknown_error` only if the probe has neither a transport status, a response-kind mismatch, a parser-empty marker, nor a recognizable auth/WAF/runtime error.
