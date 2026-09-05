FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
RUN python -m venv /opt/venv
COPY backend/requirements-runtime.txt ./requirements-runtime.txt
RUN trusted=""; if [ -n "$PIP_TRUSTED_HOST" ]; then trusted="--trusted-host $PIP_TRUSTED_HOST"; fi; \
    /opt/venv/bin/pip install --upgrade pip --index-url "$PIP_INDEX_URL" $trusted --retries 8 --timeout 120 \
    && /opt/venv/bin/pip install --index-url "$PIP_INDEX_URL" $trusted --retries 8 --timeout 120 -r requirements-runtime.txt

FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/legado_hub.db \
    NOVEL_DB_PATH=/data/novel.db \
    JAVA_TOOL_OPTIONS="-Xms32m -Xmx128m"

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --gid 10001 --home /app app \
    && mkdir -p /data /app/logs \
    && chown -R app:app /data /app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY backend/app ./app
RUN chmod -R a+rX /app/app && chown -R app:app /app/app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
