# LegadoHub Pro API 手册

版本: 2.1.0

本文档详细列出 LegadoHub Pro 所有对外 API 端点，包括 v0 兼容 API 和 v1 Pro API。

---

## 目录

1. [通用约定](#通用约定)
2. [v0 兼容 API](#v0-兼容-api)
3. [v1 Pro API](#v1-pro-api)
4. [WebSocket 实时推送](#websocket-实时推送)
5. [认证方式](#认证方式)
6. [限流说明](#限流说明)

---

## 通用约定

### 基础信息

| 项目 | 值 |
|------|-----|
| 基础 URL | `http://localhost:8000` |
| 协议 | HTTP/1.1 或 HTTP/2 |
| 编码 | UTF-8 |
| 内容类型 | `application/json` |

### 通用响应格式

所有 API 返回统一 JSON 结构：

```json
{
  "success": true,
  "code": "OK",
  "message": "操作成功",
  "data": {},
  "meta": {},
  "trace_id": "a1b2c3d4e5f67890"
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `code` | string | 业务状态码，如 `OK`、`NOT_FOUND` |
| `message` | string | 人类可读的消息 |
| `data` | any | 业务数据，成功时填充 |
| `meta` | object | 元数据（分页、统计等），可选 |
| `trace_id` | string | 链路追踪 ID，用于排查问题 |

### 分页响应格式

列表接口返回分页结构，`meta` 中包含：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [...],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 150,
    "total_pages": 8
  },
  "trace_id": "..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `meta.page` | int | 当前页码 |
| `meta.page_size` | int | 每页条数 |
| `meta.total` | int | 总记录数 |
| `meta.total_pages` | int | 总页数 |

### 错误响应格式

```json
{
  "success": false,
  "code": "ERROR_CODE",
  "message": "错误描述",
  "details": {},
  "path": "/api/xxx"
}
```

常见错误码：

| HTTP 状态码 | 业务码 | 说明 |
|-------------|--------|------|
| 400 | `VALIDATION_ERROR` | 请求参数错误 |
| 401 | `AUTHENTICATION_ERROR` | 认证失败 |
| 403 | `AUTHORIZATION_ERROR` | 权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` | 资源冲突 |
| 429 | `RATE_LIMIT_EXCEEDED` | 请求过于频繁 |
| 429 | `QUOTA_EXCEEDED` | 配额已用完 |
| 502 | `EXTERNAL_SERVICE_ERROR` | 外部服务异常 |
| 500 | `INTERNAL_ERROR` / `STORAGE_ERROR` | 服务器内部错误 |

---

## v0 兼容 API

v0 API 保持与旧版 LegadoHub 的向后兼容，无需认证即可访问（部分写操作建议配置认证）。

---

### 书源管理

#### 列出书源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/book` |
| 认证 | 可选 |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 200 |
| `search` | string | 否 | 关键词搜索 |
| `group` | string | 否 | 按分组筛选 |
| `status` | string | 否 | 按状态筛选（ok, error, unknown） |
| `enabled_only` | bool | 否 | 仅返回启用的源，默认 false |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [
    {
      "bookSourceUrl": "https://example.com",
      "bookSourceName": "示例书源",
      "bookSourceGroup": "精品",
      "enabled": true,
      "sourceStatus": "ok",
      "ruleSearch": {"bookList": "tag.li", "name": "tag.a@text"},
      "ruleToc": {"chapterList": "tag.li", "chapterName": "tag.a@text", "chapterUrl": "tag.a@href"},
      "ruleContent": {"content": "id.content@html"}
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 150,
    "total_pages": 8
  },
  "trace_id": "a1b2c3d4e5f67890"
}
```

---

#### 获取单个书源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/book/{url}` |
| 认证 | 可选 |

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `url` | string | 书源 URL（支持 path 类型） |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "bookSourceUrl": "https://example.com",
    "bookSourceName": "示例书源",
    "enabled": true,
    "sourceStatus": "ok"
  },
  "trace_id": "..."
}
```

**错误响应示例**：

```json
{
  "success": false,
  "code": "NOT_FOUND",
  "message": "书源不存在: https://example.com",
  "details": {},
  "path": "/api/sources/book/https://example.com"
}
```

---

#### 创建书源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/book` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "bookSourceUrl": "https://newsite.com",
  "bookSourceName": "新书源",
  "bookSourceGroup": "测试",
  "enabled": true,
  "searchUrl": "https://newsite.com/search?keyword={key}",
  "ruleSearch": {
    "bookList": "class.result-list@tag.li",
    "name": "class.title@text",
    "author": "class.author@text",
    "bookUrl": "tag.a@href"
  },
  "ruleToc": {
    "chapterList": "class.chapter-list@tag.li",
    "chapterName": "tag.a@text",
    "chapterUrl": "tag.a@href"
  },
  "ruleContent": {
    "content": "id.content@html"
  }
}
```

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "书源创建成功",
  "data": {
    "bookSourceUrl": "https://newsite.com",
    "bookSourceName": "新书源"
  },
  "trace_id": "..."
}
```

---

#### 更新书源

| 项目 | 值 |
|------|-----|
| 方法 | `PUT` |
| 路径 | `/api/sources/book/{url}` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "bookSourceName": "更新后的名称",
  "enabled": false
}
```

---

#### 删除书源

| 项目 | 值 |
|------|-----|
| 方法 | `DELETE` |
| 路径 | `/api/sources/book/{url}` |
| 认证 | 可选 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "书源删除成功",
  "data": null,
  "trace_id": "..."
}
```

---

#### 批量导入书源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/book/import` |
| 认证 | 可选 |

**请求体示例**：

```json
[
  {
    "bookSourceUrl": "https://site1.com",
    "bookSourceName": "书源1",
    "enabled": true
  },
  {
    "bookSourceUrl": "https://site2.com",
    "bookSourceName": "书源2",
    "enabled": true
  }
]
```

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "成功导入 2 个书源",
  "data": {"count": 2},
  "trace_id": "..."
}
```

---

### RSS 订阅源管理

#### 列出 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/rss` |
| 认证 | 可选 |

**请求参数（Query）**：与书源列表相同。

---

#### 获取单个 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/rss/{url}` |
| 认证 | 可选 |

---

#### 创建 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/rss` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "sourceUrl": "https://rss.example.com/feed.xml",
  "sourceName": "示例 RSS",
  "sourceGroup": "资讯",
  "enabled": true,
  "ruleArticles": "tag.item",
  "ruleTitle": "tag.title@text",
  "ruleLink": "tag.link@text"
}
```

---

#### 删除 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `DELETE` |
| 路径 | `/api/sources/rss/{url}` |
| 认证 | 可选 |

---

#### 批量导入 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/rss/import` |
| 认证 | 可选 |

---

### 订阅管理

#### 列出订阅

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/subscriptions` |
| 认证 | 可选 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "精品书源订阅",
      "url": "https://example.com/sub.json",
      "subType": "book",
      "enabled": true,
      "autoFetch": true,
      "fetchInterval": 3600
    }
  ],
  "trace_id": "..."
}
```

---

#### 创建订阅

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/subscriptions` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "name": "新订阅",
  "url": "https://example.com/source.json",
  "subType": "book"
}
```

---

#### 删除订阅

| 项目 | 值 |
|------|-----|
| 方法 | `DELETE` |
| 路径 | `/api/sources/subscriptions/{sub_id}` |
| 认证 | 可选 |

---

### 过滤规则管理

#### 列出过滤规则

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/sources/filters` |
| 认证 | 可选 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "过滤广告源",
      "pattern": "ad|广告",
      "isRegex": true,
      "scope": "sourceName",
      "isEnabled": true
    }
  ],
  "trace_id": "..."
}
```

---

#### 创建过滤规则

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/sources/filters` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "name": "过滤测试源",
  "pattern": "test",
  "isRegex": false,
  "scope": "sourceName",
  "isEnabled": true
}
```

---

#### 删除过滤规则

| 项目 | 值 |
|------|-----|
| 方法 | `DELETE` |
| 路径 | `/api/sources/filters/{rule_id}` |
| 认证 | 可选 |

---

### 可用性检查 (/api/health)

#### 批量检查源可用性

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/health/check` |
| 认证 | 可选 |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_type` | string | 否 | `book` 或 `rss`，不填则检查全部 |
| `limit` | int | 否 | 检查数量上限，默认 50，最大 200 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "检查完成: 45 正常, 5 异常",
  "data": {
    "results": [
      {
        "sourceUrl": "https://example.com",
        "sourceName": "示例书源",
        "sourceType": "book",
        "status": "ok",
        "responseTime": 0.8,
        "errorMsg": null,
        "checkedAt": "2024-01-15T08:30:00"
      }
    ],
    "total": 50,
    "ok": 45,
    "error": 5
  },
  "trace_id": "..."
}
```

---

#### 检查单个源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/health/check/{source_type}/{url}` |
| 认证 | 可选 |

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `source_type` | string | `book` 或 `rss` |
| `url` | string | 源 URL |

---

### 写源引擎 (/api/engine)

#### 自动生成书源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/engine/generate` |
| 认证 | 需要 Bearer Token |

**请求体示例**：

```json
{
  "url": "https://newnovel.com",
  "sourceType": "book",
  "sourceName": "新小说网"
}
```

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "自动生成完成",
  "data": {
    "source": {
      "bookSourceUrl": "https://newnovel.com",
      "bookSourceName": "新小说网",
      "searchUrl": "https://newnovel.com/search?keyword={key}",
      "ruleSearch": {"bookList": "tag.article", "name": "tag.h2@text"},
      "ruleToc": {"chapterList": "class.chapter-list@tag.li", "chapterName": "tag.a@text"},
      "ruleContent": {"content": "class.content@html"}
    },
    "logs": [
      "自动解析兼容性评分: B (75/100)",
      "自动解析质量不足，启用兼容性规则兜底...",
      "兜底后评分: A (88/100)",
      "自动修复 2 个问题",
      "书源已自动保存到数据库"
    ],
    "compatibility": {
      "score": 88,
      "grade": "A",
      "issues": [],
      "is_usable": true
    }
  },
  "trace_id": "..."
}
```

---

#### 修复已有书源

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/engine/repair` |
| 认证 | 可选 |

**请求体示例**：

```json
{
  "bookSourceUrl": "https://example.com",
  "bookSourceName": "示例书源",
  "ruleToc": {"chapterUrl": "/chapter/123"},
  "respondTime": 1000
}
```

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "source": {
      "bookSourceUrl": "https://example.com",
      "ruleToc": {"chapterUrl": "/chapter/123##$##$"},
      "respondTime": 180000,
      "header": "User-Agent: Mozilla/5.0"
    },
    "fixes": ["修复章节链接相对路径", "响应超时时间调整为180秒", "添加默认请求头"],
    "score_before": {"score": 65, "grade": "C"},
    "score_after": {"score": 85, "grade": "B"}
  },
  "trace_id": "..."
}
```

---

#### 评估书源兼容性

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/engine/evaluate` |
| 认证 | 可选 |

**请求体示例**：传入完整书源 JSON。

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "score": 88,
    "grade": "A",
    "issues": [],
    "is_usable": true
  },
  "trace_id": "..."
}
```

---

### 统一输出 (/api/output)

#### 输出书源（Legado 兼容格式）

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/output/book` |
| 认证 | 可选 |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `group` | string | 否 | 按分组筛选 |
| `enabled_only` | bool | 否 | 仅输出启用的源，默认 true |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "共 150 个书源",
  "data": [
    {
      "bookSourceUrl": "https://example.com",
      "bookSourceName": "示例书源",
      "enabled": true,
      "ruleSearch": {...},
      "ruleToc": {...},
      "ruleContent": {...}
    }
  ],
  "trace_id": "..."
}
```

---

#### 输出 RSS 源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/output/rss` |
| 认证 | 可选 |

---

#### 输出所有源

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/output/all` |
| 认证 | 可选 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "书源 150 个, 订阅源 30 个",
  "data": {
    "bookSources": [...],
    "rssSources": [...],
    "totalBookSources": 150,
    "totalRssSources": 30
  },
  "trace_id": "..."
}
```

---

#### 导出 JSON 文件

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/output/export.json` |
| 认证 | 可选 |

返回 `Content-Disposition: attachment; filename=sources.json` 的纯 JSON 文件，可直接导入 Legado App。

---

## v1 Pro API

v1 API 提供增强功能，包括认证授权、AI 分析和配额管理。部分接口需要管理员权限。

---

### 认证与授权 (/api/v1/auth)

#### 管理员登录

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/auth/login` |
| 认证 | 无需认证 |

**请求参数（Form / Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 管理员用户名 |
| `password` | string | 是 | 管理员密码 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "username": "admin",
      "role": "admin"
    }
  },
  "trace_id": "..."
}
```

**错误响应示例**：

```json
{
  "success": false,
  "code": "AUTHENTICATION_ERROR",
  "message": "用户名或密码错误",
  "details": {},
  "path": "/api/v1/auth/login"
}
```

---

#### 初始化管理员

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/auth/setup` |
| 认证 | 无需认证（首次部署使用） |

**请求参数（Form / Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 管理员用户名 |
| `password` | string | 是 | 管理员密码 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "管理员创建成功",
  "data": null,
  "trace_id": "..."
}
```

**错误响应示例**：

```json
{
  "success": false,
  "code": "CONFLICT",
  "message": "管理员已存在",
  "details": {},
  "path": "/api/v1/auth/setup"
}
```

---

#### 列出 API Key

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/auth/keys` |
| 认证 | Bearer Token（需管理员权限） |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [
    {
      "id": 1,
      "key_hash": "a1b2c3d4...",
      "name": "生产环境Key",
      "is_enabled": true,
      "permissions": {"source_read": true, "export": true},
      "key_masked": "a1b2****c3d4"
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 5,
    "total_pages": 1
  },
  "trace_id": "..."
}
```

**错误响应示例**：

```json
{
  "success": false,
  "code": "AUTHORIZATION_ERROR",
  "message": "Admin permission required",
  "details": {},
  "path": "/api/v1/auth/keys"
}
```

---

#### 创建 API Key

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/auth/keys` |
| 认证 | Bearer Token（需管理员权限） |

**请求体示例**：

```json
{
  "name": "新应用Key",
  "permissions": {
    "source_read": true,
    "source_import": true,
    "ai_character": true,
    "export": true
  }
}
```

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "API Key 创建成功",
  "data": {
    "api_key": "lh_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345",
    "key_id": 2,
    "name": "新应用Key",
    "permissions": {"source_read": true, "source_import": true, "ai_character": true, "export": true}
  },
  "trace_id": "..."
}
```

**注意**：`api_key` 仅在创建时返回一次，请妥善保存。

---

#### 删除 API Key

| 项目 | 值 |
|------|-----|
| 方法 | `DELETE` |
| 路径 | `/api/v1/auth/keys/{key_id}` |
| 认证 | Bearer Token（需管理员权限） |

---

#### 查询配额

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/auth/quota` |
| 认证 | Bearer Token（API Key 或 JWT） |

**成功响应示例（API Key）**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "fetch": {
      "used": 120,
      "total": 500
    },
    "ai": {
      "used": 15000,
      "total": 100000
    },
    "storage_mb": {
      "used": 256.5,
      "total": 1024
    }
  },
  "trace_id": "..."
}
```

**成功响应示例（JWT 管理员）**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {"unlimited": true},
  "trace_id": "..."
}
```

---

#### 列出用户

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/auth/users` |
| 认证 | Bearer Token（需管理员权限） |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |

---

#### 审计日志

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/auth/audit` |
| 认证 | Bearer Token（需管理员权限） |

**请求参数（Query）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 否 | 按操作类型筛选 |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": [
    {
      "id": 1,
      "api_key_id": 1,
      "action": "POST /api/sources/book",
      "resource_type": "api",
      "resource_id": "/api/sources/book",
      "details": {
        "method": "POST",
        "path": "/api/sources/book",
        "status_code": 200,
        "duration_ms": 45.2,
        "client_ip": "192.168.1.1"
      },
      "ip_address": "192.168.1.1",
      "createdAt": "2024-01-15T08:30:00"
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 1000,
    "total_pages": 50
  },
  "trace_id": "..."
}
```

---

#### 验证 Token

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/auth/verify` |
| 认证 | Bearer Token |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "valid": true,
    "is_admin": false,
    "permissions": {"source_read": true, "export": true},
    "api_key_id": 1,
    "user_id": null,
    "username": null
  },
  "trace_id": "..."
}
```

---

### AI 增强服务 (/api/v1/llm)

AI 接口需要 Bearer Token 认证，并消耗 AI 字符配额。

#### 人物关系提取

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/character` |
| 认证 | Bearer Token |

**请求参数（Query / Form）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `book_url` | string | 是 | 书源 URL |
| `book_name` | string | 否 | 书名 |
| `sample_text` | string | 否 | 样本文本（前 3000 字符有效） |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "book_url": "https://example.com/novel/123",
    "book_name": "示例小说",
    "characters": "{\"mock\": true, \"message\": \"LLM API 未配置，使用模拟数据\"}",
    "mock": true
  },
  "trace_id": "..."
}
```

---

#### 世界观解析

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/world` |
| 认证 | Bearer Token |

**请求参数**：与人物关系提取相同。

---

#### 剧情时间线

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/storyline` |
| 认证 | Bearer Token |

**请求参数（Query / Form）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `book_url` | string | 是 | 书源 URL |
| `book_name` | string | 否 | 书名 |
| `chapters` | list | 否 | 章节列表（前 20 章有效） |

---

#### 智能问答

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/chat` |
| 认证 | Bearer Token |

**请求参数（Query / Form）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `book_url` | string | 是 | 书源 URL |
| `question` | string | 是 | 问题内容 |
| `context` | string | 否 | 上下文（前 2000 字符有效） |

---

#### 书源修复建议

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/fix` |
| 认证 | Bearer Token |

**请求参数（Query / Form）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_url` | string | 是 | 书源 URL |
| `error_msg` | string | 否 | 错误信息 |
| `source_config` | object | 否 | 当前书源配置 |

---

#### 内容合规审查

| 项目 | 值 |
|------|-----|
| 方法 | `POST` |
| 路径 | `/api/v1/llm/review` |
| 认证 | Bearer Token |

**请求参数（Query / Form）**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 待审查文本（前 5000 字符有效） |

---

#### 获取人物关系缓存结果

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/llm/character/{book_url}` |
| 认证 | Bearer Token |

---

#### 获取世界观缓存结果

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/llm/world/{book_url}` |
| 认证 | Bearer Token |

---

#### 获取剧情时间线缓存结果

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/v1/llm/storyline/{book_url}` |
| 认证 | Bearer Token |

---

## WebSocket 实时推送

### 连接端点

| 项目 | 值 |
|------|-----|
| 协议 | WebSocket (`ws://` 或 `wss://`) |
| 路径 | `/api/ws/events` |
| 认证 | 连接后通过 `auth` 动作认证 |

### 客户端消息

连接成功后，客户端可发送以下 JSON 消息：

**订阅频道**：

```json
{
  "action": "subscribe",
  "channels": ["task_progress", "source_status", "system_notice"]
}
```

**取消订阅**：

```json
{
  "action": "unsubscribe",
  "channels": ["task_progress"]
}
```

**心跳**：

```json
{"action": "ping"}
```

**认证（升级为管理员推送）**：

```json
{
  "action": "auth",
  "token": "lh_xxxxxxxx"
}
```

### 服务端推送消息

**连接成功**：

```json
{
  "type": "connected",
  "message": "WebSocket 连接成功",
  "timestamp": "2024-01-15T08:30:00"
}
```

**任务进度**：

```json
{
  "type": "task_progress",
  "task_id": "fetch-123",
  "progress": 75,
  "message": "正在拉取第 15/20 个源",
  "timestamp": "2024-01-15T08:30:00"
}
```

**源状态变更**：

```json
{
  "type": "source_status",
  "source_url": "https://example.com",
  "source_name": "示例书源",
  "status": "error",
  "timestamp": "2024-01-15T08:30:00"
}
```

**系统通知**：

```json
{
  "type": "system_notice",
  "title": "维护通知",
  "content": "系统将于今晚 02:00 进行维护",
  "level": "info",
  "timestamp": "2024-01-15T08:30:00"
}
```

**配额告警（仅管理员）**：

```json
{
  "type": "quota_alert",
  "api_key_id": 1,
  "metric": "ai_chars",
  "used": 95000,
  "limit": 100000,
  "usage_percent": 95.0,
  "timestamp": "2024-01-15T08:30:00"
}
```

---

## 认证方式

LegadoHub Pro 支持两种认证方式：Bearer API Key 和 Bearer JWT Token。

### Bearer API Key

用于应用接入和日常 API 调用。Key 格式为 `lh_` 前缀 + 32 位随机字符。

**请求头**：

```http
Authorization: Bearer lh_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345
```

**特点**：
- 永久有效（除非手动禁用或设置过期时间）
- 可配置细粒度权限
- 受配额限制
- 支持审计追踪

### Bearer JWT Token

用于管理员登录和后台管理。

**请求头**：

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**获取方式**：调用 `POST /api/v1/auth/login` 获取。

**特点**：
- 默认有效期 24 小时
- 拥有管理员权限时不受配额限制
- 适合临时操作和后台管理

### 认证失败响应

当请求缺少认证头或凭证无效时，返回 401 状态码：

```json
{
  "success": false,
  "code": "AUTHENTICATION_ERROR",
  "message": "Missing Authorization header",
  "details": {},
  "path": "/api/v1/llm/character"
}
```

响应头包含：

```http
WWW-Authenticate: Bearer
```

---

## 限流说明

### 限流策略

系统使用基于 Redis 的滑动窗口限流算法。默认限制：每分钟 60 请求。

限流 Key 优先级：
1. 如果请求携带 `Bearer lh_` 开头的 API Key，按 Key 前缀限流
2. 否则按客户端 IP 限流

### 限流响应头

所有 API 响应（除静态文件和文档）包含以下头：

| 响应头 | 说明 |
|--------|------|
| `X-RateLimit-Limit` | 每分钟请求上限 |
| `X-RateLimit-Remaining` | 当前窗口剩余请求数 |
| `X-RateLimit-Reset` | 窗口重置剩余秒数（被限流时） |
| `X-Process-Time` | 请求处理耗时（秒） |

### 触发限流

当请求超过限制时，返回 429 状态码：

```json
{
  "success": false,
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded. Try again in 30s."
}
```

响应头：

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 30
Retry-After: 30
```

### 降级策略

当 Redis 不可用时，限流自动降级为无限制模式，系统会在日志中记录警告：

```
[RateLimit] Redis 未连接，限流降级为无限制
```

---

## 附录：公共状态端点

### 服务状态

| 项目 | 值 |
|------|-----|
| 方法 | `GET` |
| 路径 | `/api/status` |
| 认证 | 无需认证 |

**成功响应示例**：

```json
{
  "success": true,
  "code": "OK",
  "message": "LegadoHub Pro is running",
  "version": "2.1.0",
  "architecture": "DDD",
  "storage": "sqlite"
}
```
