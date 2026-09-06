from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = os.environ.get("LEGADO_API_BASE", "http://127.0.0.1:8000/api").rstrip("/")
LLM_BASE = os.environ.get("LLM_API_URL", "").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
OUT = Path(os.environ.get("FLOW_REPORT", "/tmp/legado-hub/full-flow-report.json"))
TOKEN = ""
EVENTS: list[dict] = []


def safe_url(url: str) -> str:
    return url.split("?", 1)[0]


def request(method: str, path: str, *, body=None, headers=None, timeout=120):
    started = time.monotonic()
    payload = None if body is None else (body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode())
    req_headers = {"Accept": "application/json", "User-Agent": "legado-hub-full-flow/2.0"}
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
    if TOKEN:
        req_headers["Authorization"] = f"Bearer {TOKEN}"
    req_headers.update(headers or {})
    url = path if path.startswith(("http://", "https://")) else f"{BASE}{path}"
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


def multipart_request(path: str, fields: dict[str, str], file_path: Path, timeout=600):
    boundary = f"----legado-flow-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:20]}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(), str(value).encode(), b"\r\n"]
    chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\nContent-Type: text/plain\r\n\r\n'.encode(), file_path.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode()]
    return request("POST", path, body=b"".join(chunks), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=timeout)


def summarize(value):
    if not isinstance(value, dict):
        return value
    data = value.get("data") if isinstance(value.get("data"), dict) else {}
    preview = data.get("preview") if isinstance(data.get("preview"), dict) else data
    result = {"success": value.get("success"), "code": value.get("code"), "message": value.get("message")}
    for key in ("book_id", "duplicate", "status", "task_id", "error_code", "work_id", "chapter_count", "total_chars", "content_hash"):
        if key in data or key in preview:
            result[key] = data.get(key, preview.get(key))
    if isinstance(preview.get("chapters"), list):
        result["chapter_count"] = len(preview["chapters"])
    if isinstance(data.get("report"), dict):
        result["report_counts"] = {k: len(data["report"].get(k, [])) for k in ("characters", "events", "time_mentions", "cooccurrences") if isinstance(data["report"].get(k), list)}
    return result


def main() -> int:
    global TOKEN
    report = {"base": BASE, "llm_base": LLM_BASE, "novels": [], "source_validation": [], "events": EVENTS, "errors": []}
    status, value = request("GET", "/status", timeout=30)
    report["status"] = {"http": status, "summary": summarize(value)}
    user, password = os.environ.get("LEGADO_LOGIN_USER"), os.environ.get("LEGADO_LOGIN_PASSWORD")
    if user and password:
        status, value = request("POST", "/auth/login", body={"username": user, "password": password}, timeout=30)
        TOKEN = value.get("data", {}).get("access_token", "") if status == 200 and isinstance(value, dict) else ""
        if not TOKEN:
            report["errors"].append({"stage": "login", "status": status, "summary": summarize(value)})
    else:
        report["errors"].append({"stage": "login", "error": "credentials not provided; no credential guessing performed"})

    if TOKEN:
        source_path = Path(os.environ.get("SOURCE_FILE", "/tmp/yiove-book-sources-page-1-20.json"))
        if source_path.exists():
            status, value = request("POST", "/sources/import", body=json.loads(source_path.read_text(encoding="utf-8")), timeout=180)
            report["source_import"] = {"status": status, "summary": summarize(value), "source_count": len(json.loads(source_path.read_text(encoding="utf-8")))}
            if status != 200:
                report["errors"].append({"stage": "source_import", "status": status, "summary": summarize(value)})

        for novel in sorted(Path("/txt").glob("*.txt")):
            item = {"file": novel.name, "bytes": novel.stat().st_size, "sha256": hashlib.sha256(novel.read_bytes()).hexdigest()}
            status, value = multipart_request("/novel/books/import/preview", {"split_mode": "heading", "min_chapter_chars": "20"}, novel)
            item["preview"] = {"status": status, "summary": summarize(value)}
            if status != 200:
                report["errors"].append({"stage": "novel_preview", "file": novel.name, "status": status, "summary": summarize(value)})
                report["novels"].append(item)
                continue
            status, value = multipart_request("/novel/books/import/upload", {"split_mode": "heading", "min_chapter_chars": "20"}, novel)
            item["import"] = {"status": status, "summary": summarize(value)}
            book_id = value.get("data", {}).get("book_id") if isinstance(value, dict) else None
            if book_id:
                status, chapters = request("GET", f"/novel/books/{book_id}/chapters", timeout=180)
                item["chapters"] = {"status": status, "total": chapters.get("meta", {}).get("total") if isinstance(chapters, dict) else None}
                status, analysis = request("POST", f"/novel/books/{book_id}/analysis", timeout=600)
                item["llm_analysis"] = {"status": status, "summary": summarize(analysis)}
            if status != 200:
                report["errors"].append({"stage": "novel_import_or_analysis", "file": novel.name, "status": status, "summary": summarize(value)})
            report["novels"].append(item)

        status, value = request("POST", "/reading/search", body={"keyword": "天才俱乐部", "limit_per_source": 3}, timeout=180)
        report["source_search"] = {"status": status, "summary": summarize(value)}
    else:
        report["errors"].append({"stage": "authenticated_flow", "error": "skipped because authentication was unavailable"})

    if LLM_BASE:
        status, value = request("GET", f"{LLM_BASE}/models", headers={"Authorization": f"Bearer {LLM_KEY}"}, timeout=60)
        if isinstance(value, dict):
            value = {"object": value.get("object"), "model_count": len(value.get("data", [])) if isinstance(value.get("data"), list) else None}
        report["llm_probe"] = {"status": status, "summary": value, "key_configured": bool(LLM_KEY)}
        if status != 200:
            report["errors"].append({"stage": "llm_probe", "status": status, "summary": value})

    report["events"] = EVENTS
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(OUT), "errors": len(report["errors"]), "events": len(EVENTS)}, ensure_ascii=False))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
