FROM gradle:9.6.1-jdk17 AS legado-runtime-builder

WORKDIR /runtime
COPY runtime/legado-kotlin/ ./
RUN gradle installDist --no-daemon

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    chromium \
    libxml2-dev \
    libxslt1-dev \
    openjdk-17-jre-headless \
    tini \
    websockify \
    x11vnc \
    xvfb \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nodejs/ ./nodejs/
RUN npm ci --prefix ./nodejs

COPY app/ ./app/
COPY --from=legado-runtime-builder /runtime/build/install/legado-kotlin-runtime/ /app/runtime/

ENV DB_PATH=/data/legado_hub.db
ENV NOVEL_DB_PATH=/data/novel.db
ENV PYTHONUNBUFFERED=1
ENV LEGADO_RUNTIME_COMMAND=/app/runtime/bin/legado-kotlin-runtime
ENV JAVA_TOOL_OPTIONS="-Xms32m -Xmx256m"

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
