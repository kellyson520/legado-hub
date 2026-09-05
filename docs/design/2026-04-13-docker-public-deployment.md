# LegadoHub Docker 公网部署设计

## 目标

为 LegadoHub 提供低内存、可更新、可持久化的 Docker Compose 部署，并支持通过 Cloudflare Tunnel 安全发布到公网。

## 背景与约束

- 目标仓库：`https://github.com/kellyson520/legado-hub`。
- 当前项目使用 FastAPI + React/Vite + SQLite；已有 API 入口为 `backend/app/main.py`。
- 现有 Dockerfile 包含 JVM、Gradle、Chromium、X11VNC、Node 等重型依赖，必须拆除非默认运行路径的构建负担。
- 不把 Redis、MinIO、SQLite、日志或密钥暴露到公网。
- 所有持久数据必须落到宿主机挂载目录，便于备份和后续替换源码。
- 不在仓库内写入 GitHub token、LLM key、Cloudflare token 或生产 secret。

## 方案

1. `backend/Dockerfile` 使用 Python slim 多阶段构建：builder 安装 wheel，runtime 只安装运行依赖，使用非 root 用户和 `tini`。
2. `frontend/Dockerfile` 使用 Node builder 编译静态文件，再由 Nginx alpine 提供静态资源并反代 `/api` 到 API 服务。
3. `docker-compose.yml` 默认只启动 `api` 和 `web`；`redis`、`minio`、`tunnel` 使用 profiles 显式启用。
4. `docker-compose.public.yml` 或 Compose profile 使用 `cloudflared`，仅把 `web:80` 发布到用户自己的 Cloudflare Tunnel hostname。
5. `./backend/app`、`./frontend/src` 在开发 override 中挂载；生产默认使用镜像内源码，数据通过 `./data`、`./logs`、`./backups` 挂载。

## 资源控制

- API 默认单 worker、无 reload。
- JVM/浏览器/Legado native runtime 不进入默认 API 镜像；默认设置 `LEGADO_RUNTIME_HEALTHCHECK_ENABLED=false`，只有搭配独立 runtime 镜像时才启用该探测。
- Redis 使用 `maxmemory 64mb`，不发布宿主端口。
- Compose 为 API 设置 `mem_limit: 512m`，Web `64m`，Redis `96m`。
- Nginx 开启 gzip 和连接复用，静态资源不经过 Python。

## 公网与安全

- 默认只暴露 `127.0.0.1:8080`，不直接绑定 `0.0.0.0`。
- 公网模式由 Cloudflare Tunnel 出站连接提供，无需开放入站端口。
- Tunnel token 只通过 `.env` 或宿主 secret 注入，不提交 Git。
- `SECRET_KEY` 必须由部署者生成，禁止使用示例值。

## 验收标准

1. `docker compose config` 成功且默认服务不发布 Redis/MinIO 端口。
2. API 镜像可构建，容器以非 root 用户运行，healthcheck 成功。
3. 前端镜像可构建，Nginx 正确代理 `/api`。
4. SQLite、小说文件和日志目录均为 bind mount。
5. `docker compose --profile public config` 可渲染 Cloudflare Tunnel 配置；没有 token 时不启动公网服务。
6. Git diff 无密钥、构建缓存和数据库文件。
7. 目标 GitHub remote 经确认后才执行 push；没有 remote/认证时只提交本地并明确阻塞。
