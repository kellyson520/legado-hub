# 统一服务端分页与列表模块设计

## 目标

将控制台中所有可增长的列表页统一为服务端分页、可选服务端搜索和一致的加载/错误/重试行为，避免页面一次性读取全部记录、重复实现请求竞态保护，并让列表页能够在相同数据契约下快速扩展。

## 背景与现状

当前前端列表页存在三种实现方式：

- 书源库存已经具备服务端分页和搜索，但页面内仍有大量专用请求状态代码。
- 书源健康页有自己的分页和竞态保护实现，分页控件与库存页不一致。
- 任务、审核、构建、Agent、用户、审计、翻译和小说等页面直接调用无分页列表接口，把全部数据加载到浏览器后再渲染。

后端接口的 `meta` 字段也不统一，有的只有 `total`，有的包含 `page_size`，搜索和总页数缺少统一约定。

## 设计原则

1. 服务端负责过滤、排序、分页和总数统计；浏览器只保留当前页数据。
2. 请求状态、过期响应保护和重试目标由一个通用 hook 管理；行内操作、详情抽屉和 SSE 订阅仍由页面自己管理。
3. 分页和搜索是可选能力。没有合理搜索字段的列表只启用分页，不强行添加客户端过滤。
4. 新字段优先以向后兼容方式加入响应；省略查询参数时保持现有默认行为。
5. 统一基础模块，不进行与本目标无关的视觉重做、全局状态库替换或虚拟列表引入。

## 前端模块

### `useServerPagination`

新增 `frontend/src/hooks/useServerPagination.ts`，提供泛型列表状态：

```ts
interface ServerPageRequest {
  page: number
  pageSize: number
  search: string
}

interface ServerPageMeta {
  page: number
  pageSize: number
  total: number
  totalPages: number
  search: string
}

interface UseServerPaginationOptions<T> {
  pageSize: number
  load: (request: ServerPageRequest) => Promise<ApiEnvelope<T[]>>
  initialSearch?: string
}
```

返回当前 `rows`、`meta`、输入搜索词、应用搜索词、加载状态、错误状态，以及 `submitSearch`、`clearSearch`、`goToPage`、`retry` 和 `reload` 操作。实现要求：

- 首次加载请求第 1 页。
- 搜索词 `trim()` 后发送，并始终请求第 1 页。
- 翻页请求只替换 `rows`，禁止追加上一页。
- 每次请求记录 `{page, search}` 作为重试目标。
- 用递增 request id 丢弃过期响应；卸载后不更新状态。
- 对缺失或非法 `meta` 使用安全回退值，避免 NaN 页码。

### `PaginationToolbar`

新增 `frontend/src/components/data/PaginationToolbar.tsx`，统一渲染：

- 可选的搜索输入、搜索按钮和清空按钮。
- 当前页、总页数和总记录数。
- 上一页/下一页按钮及禁用状态。
- `aria-label`、按钮名称和加载状态的统一中文文案。

组件只接收数据和回调，不直接调用 API，确保可以在不同列表页和测试中复用。

### API 类型

在 `frontend/src/api/types.ts` 增加可复用的分页元数据类型；各 API 模块的列表参数统一使用 `page`、`page_size`、`search`，额外过滤条件以明确的可选字段扩展。所有列表响应的 `meta` 至少返回：

```json
{
  "page": 1,
  "page_size": 20,
  "total": 0,
  "total_pages": 0,
  "search": ""
}
```

## 后端接口与服务

### 现有分页页迁移

- `/api/sources/visible` 保留当前搜索和分页行为，补齐 `total_pages`。
- `/api/sources/health` 保留状态过滤，统一返回 `total_pages`；前端改用通用 hook。

### 需要补齐分页的列表接口

按业务域扩展查询参数、服务方法和仓储查询，且在数据库层完成 `COUNT/OFFSET/LIMIT`：

- 操作与审核：`/events/jobs`、`/events/deliveries`、`/events/agent-runs`、`/events/review-queue`、`/events/source-builds`。
- 管理：`/admin/users`、`/admin/audit`、`/admin/api-keys`。
- 运行与内容：`/engine/runs`、`/engine/deployments`、`/engine/source-builds`、`/ai/tasks`、`/ai/conversations`、`/novel/books`、`/translation/jobs`。

搜索只针对有稳定字段的列表启用，例如任务类型、状态、租户、源 URL、用户名、事件类型、书名和语言；状态、租户等结构化筛选保留为独立参数，不拼接到自由文本搜索中。详情、创建、更新、审核和 SSE 流接口不改为分页接口。

## 页面迁移顺序

1. 抽取 hook、toolbar 和 meta 规范；迁移书源库存和健康诊断，确保现有行为不回归。
2. 迁移操作页：任务、事件投递、构建候选、审核队列和 Agent runs；详情请求和行内审核动作保持原逻辑。
3. 迁移管理与内容页：用户、审计、AI 任务/会话、引擎运行、小说任务、翻译任务。
4. 删除各页面重复的分页计算、过期请求保护和空状态代码；保留旧的未路由页面兼容层，待路由确认后再清理。

## 错误、并发与性能

- 翻页或搜索期间禁用对应控件，但保留已显示的上下文信息。
- 请求失败显示页面级错误和“重试”；重试使用失败请求的页码与搜索词。
- 快速连续搜索或翻页时，只有最后一次请求可以更新页面。
- 默认页大小按业务设置上限，后端拒绝过大的 `page_size`。
- 不在 hook 中缓存所有页；需要刷新时只重新请求当前查询条件的当前页。

## 测试策略

### 前端基础模块

- hook 首次加载、页间替换、搜索回到第 1 页、清空搜索。
- 失败页和失败搜索的重试目标。
- 过期响应、卸载期间响应和非法 meta 的安全回退。
- toolbar 的禁用状态、无障碍名称和无结果文案。

### 后端接口

- 搜索先过滤再分页，`total` 与 `total_pages` 正确。
- 页码边界、空结果、非法页大小和结构化筛选。
- 权限、租户/用户可见性和详情接口不回归。

### 页面回归

每迁移一个页面，保留其现有行内动作测试，并增加至少一个服务端分页/搜索请求断言。完成后运行相关 pytest、Vitest 和生产构建。

## 非目标

- 本次不引入虚拟滚动、React Query 等新的全局数据缓存层。
- 不改变审核、Agent 工具调用、书源解析和登录权限业务规则。
- 不将详情内容、审计证据或大文本 payload 预加载到列表响应中。

