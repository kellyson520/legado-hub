from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_compose_uses_local_web_binding_and_persistent_mounts():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert '127.0.0.1:${WEB_PORT:-8080}:80' in compose
    assert "./data:/data" in compose
    assert "./logs:/app/logs" in compose
    assert "permissions" in compose
    assert "chown -R 10001:10001 /data /logs /backups" in compose
    assert "./backups:/backups" in compose
    assert "mem_limit: 512m" in compose
    assert "mem_limit: 64m" in compose
    assert "user: root" in compose
    assert "required: false" in compose
    assert "LLM_API_URL: ${LLM_API_URL:-}" in compose
    assert "LLM_API_KEY: ${LLM_API_KEY:-}" in compose
    assert "LLM_MODEL: ${LLM_MODEL:-gpt-4.1-mini}" in compose
    assert "change-this-minio-password" not in compose

    public = (ROOT / "docker-compose.public.yml").read_text()
    assert "CLOUDFLARE_TUNNEL_TOKEN:?" in public


def test_default_compose_does_not_publish_internal_services():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert 'image: redis:7-alpine' in compose
    assert 'ports:' not in compose.split('  redis:', 1)[1]

    minio = (ROOT / "docker-compose.minio.yml").read_text()
    assert 'image: minio/minio:' in minio
    assert 'MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?' in minio


def test_nginx_proxies_api_and_supports_spa_fallback():
    nginx = (ROOT / "nginx/nginx.conf").read_text()

    assert "proxy_pass http://api;" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx
