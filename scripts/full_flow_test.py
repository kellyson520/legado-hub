from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.environ.get("LEGADO_API_BASE", "http://127.0.0.1:8000/api").rstrip("/")
LLM_BASE = os.environ.get("LLM_API_URL", "").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
OUT = Path(os.environ.get("FLOW_REPORT", "/tmp/legado-hub/full-flow-report.json"))
EVENTS: list[dict] = []
TOKEN = ""


def safe_url(url: str) -> str:
    return url.split("?", 1)[0]


def request(method: str, path: str, *, body=None, headers=None, timeout=120):
    started = time.monotonic()
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req_headers = {"Accept": "application/json", "User-Agent": "legado-hub-full-flow/1.0"}
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
    if TOKEN:
        req_headers["Authorization"] = f"Bearer {TOKEN}"
    req_headers.update(headers or {})
    url = path if path.startswith("http") else f"{BASE}{path}"
    record = {"method": method, "path": safe_url(url), "started_at": time.time()}
    try:
        with urlopen(Request(url, data=payload, headers=req_headers, method=method), timeout=timeout) as response:
            raw = response.read()
            value = json.loads(raw) if raw else None
            record.update({"status": response.status, "elapsed_ms": round((time.monotonic() - started) * 1000, 1), "response_bytes": len(raw), "ok": 200 <= response.status < 300})
            EVENTS.append(record)
            return response.status, value
    except HTTPError as exc:
        raw = exc.read(4096)
        try:
            value = json.loads(raw)
        except Exception:
            value = raw.decode("utf-8", "replace")[:500]
        record.update({"status": exc.code, "elapsed_ms": round((time.monotonic() - started) * 1000, 1), "ok": False, "error": value})
        EVENTS.append(record)
        return exc.code, value
    except (URLError, TimeoutError, OSError) as exc:
        record.update({"status": None, "elapsed_ms": round((time.monotonic() - started) * 1000, 1), "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        EVENTS.append(record)
        return None, None


def main():
    global TOKEN
    report = {"base": BASE, "llm_base": LLM_BASE, "novels": [], "events": EVENTS, "errors": []}
    status, value = request("GET", "/status", timeout=30)
    report["status"] = {"http": status, "body": value}
    if status != 200:
        report["errors"].append({"stage": "status", "status": status, "body": value})
    # Authentication is intentionally delegated to the existing deployment's first-run flow.
    login_user = os.environ.get("LEGADO_LOGIN_USER")
    login_password = os.environ.get("LEGADO_LOGIN_PASSWORD")
    if login_user and login_password:
        status, value = request("POST", "/auth/login", body={"username": login_user, "password": login_password}, timeout=30)
        if status == 200 and isinstance(value, dict):
            TOKEN = value.get("data", {}).get("access_token", "")
        else:
            report["errors"].append({"stage": "login", "status": status, "body": value})
    else:
        report["errors"].append({"stage": "login", "error": "LEGADO_LOGIN_USER/PASSWORD not provided; no credential guessing performed"})
    source_path = os.environ.get("SOURCE_FILE", "/tmp/yiove-book-sources-page-1-20.json")
    if TOKEN and Path(source_path).exists():
        payload = json.loads(Path(source_path).read_text())
        status, value = request("POST", "/sources/import", body=payload, timeout=180)
        report["source_import"] = {"status": status, "body": value, "source_count": len(payload)}
        if status != 200:
            report["errors"].append({"stage": "source_import", "status": status, "body": value})
    elif not TOKEN:
        report["errors"].append({"stage": "source_import", "error": "skipped because authentication was unavailable"})
    for novel in sorted(Path("/txt").glob("*.txt")):
        digest = hashlib.sha256(novel.read_bytes()).hexdigest()
        report["novels"].append({"file": novel.name, "bytes": novel.stat().st_size, "sha256": digest, "status": "not_uploaded_without_auth"})
    if LLM_BASE:
        status, value = request("GET", f"{LLM_BASE}/models", headers={"Authorization": f"Bearer {LLM_KEY}"}, timeout=60)
        if isinstance(value, dict):
            value.pop("data", None)
        report["llm_probe"] = {"status": status, "body": value, "key_configured": bool(LLM_KEY)}
        if status != 200:
            report["errors"].append({"stage": "llm_probe", "status": status, "body": value})
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"report": str(OUT), "errors": len(report["errors"]), "events": len(EVENTS)}, ensure_ascii=False))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
