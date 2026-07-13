# Legado Hub 中文管理、书源规则与 Agent 工作台设计

## 目标

将现有 Legado Hub 建设为一个可用的中文书源与小说分析工作台：全中文用户界面、管理员/普通用户权限、Legado JSON 书源导入导出、可验证的规则中心，以及能使用受控内容来源的 Agent 对话与剧情分析。

## 范围与交付顺序

本需求拆分为三个可独立验收的实施包，按顺序上线：

1. **中文化与用户权限基础**：全局中文文案、管理员/普通用户、用户管理和后端强制授权。
2. **书源与规则中心**：Legado JSON 导入导出、候选版本审核、规则编辑、正则测试和 full-chain probe。
3. **Agent 小说工作台**：对话会话、剧情/人物预设任务、章节/文本/URL 受控输入、AI 任务与证据审计。

任何阶段都不得用前端隐藏代替后端权限校验；书源规则和 AI 自动修复仍必须保持 candidate-only，不能自动发布。

## 角色与授权

角色只有 `admin` 与 `user`。

| 能力 | admin | user |
| --- | --- | --- |
| 概览、已发布书源、Agent 工作台 | 允许 | 允许 |
| 创建候选书源 | 允许 | 允许 |
| 导入 Legado JSON | 允许 | 允许，结果只能成为候选 |
| 导出书源 | 全部已发布和本人候选 | 已发布和本人候选 |
| 发布、审核、删除规则/书源 | 允许 | 拒绝 |
| Provider、密钥、全量 AI 任务审计 | 允许 | 拒绝 |
| 用户管理 | 允许 | 拒绝 |
| AI 任务与 Agent 历史 | 全部 | 仅本人任务 |

后端 API 使用当前认证身份作为唯一权限依据。普通用户访问管理员路由一律返回稳定的 `403` 错误码，前端映射为中文权限提示。

## 第一阶段：中文化与用户管理

### 前端

前端建立集中式中文文案表，而不是分散硬编码。导航固定使用：

```text
概览、书源管理、规则中心、AI 工作台、AI 任务、用户管理、系统设置
```

仅管理员可看见“用户管理”和“系统设置”。状态文本统一映射为：

```text
候选中、排队中、运行中、已成功、已失败、需人工审核、已发布、已停用
```

接口错误以稳定 code 映射成中文；不向用户展示 provider 原始 Authorization、Bearer、API key 或堆栈文本。

### 后端用户 API

管理员接口：

```text
GET    /api/admin/users
POST   /api/admin/users
PATCH  /api/admin/users/{id}
POST   /api/admin/users/{id}/reset-password
POST   /api/admin/users/{id}/enable
POST   /api/admin/users/{id}/disable
```

用户记录公开字段为：

```text
id、username、display_name、role、status、created_at、last_login_at
```

密码仅接受写入，不允许查询或回显。禁止管理员禁用自身、删除最后一个启用管理员，或把最后一个启用管理员降级为普通用户。

## 第二阶段：书源与规则中心

### Legado JSON 导入导出

导入端点只接受 JSON，兼容单个 Legado source object 或 source object 数组。导入器必须：

1. 验证 `bookSourceUrl`、`bookSourceName` 和规则字段的对象类型；
2. 忽略或拒绝任何系统内部字段、API key、认证 cookie 和 agent 审计字段；
3. 将每个有效条目保存为 candidate source version；
4. 返回逐条状态：`created`、`skipped_duplicate`、`invalid`；
5. 绝不因为导入而直接发布。

导出端点只输出 Legado 兼容字段，不输出系统用户、AI、认证、审计或 provider 配置。管理员可导出所有已发布书源及自己的候选；普通用户只能导出已发布和本人候选。

### 规则中心

规则中心页面编辑：

```text
书源地址、书源名称、搜索 URL、请求头、搜索规则、书籍详情规则、目录规则、正文规则、替换规则
```

提供独立正则测试器，输入文本、表达式及可选替换式，返回匹配数量、每个捕获组、替换预览或语法错误。它不执行代码、不访问网络、不执行 JavaScript。

规则测试调用既有 deterministic full-chain probe：search → toc → content。只有三段验证通过，管理员才能发布候选版本。验证页特征必须展示为：

```text
正文访问受阻：verification_wall
```

不能以 selector 存在、搜索成功或目录成功冒充可以发布。

## 第三阶段：Agent 小说工作台

### 会话与任务

每位用户拥有自己的对话会话。会话含标题、消息、输入来源引用、关联 AI task、模型用量和 agent tool 审计。预设任务为：

```text
剧情解析、章节摘要、人物介绍、人物关系、世界观与设定、时间线、伏笔与线索、自由问答
```

分析结果必须包含结构化文本及引用来源；模型没有证据时应明确说明“资料不足”，不能假造章节事实。

### 受控内容来源

用户可组合以下输入：

1. 已保存书籍或章节；
2. 直接粘贴文本；
3. 指定 HTTP/HTTPS URL。

URL 仅通过服务端受控抓取器读取，禁止模型自行联网。抓取器拒绝私有/回环/链路本地 IP、非 HTTP(S) 协议，限制重定向次数、响应体大小与总超时。抓取后的文本被截断并作为 evidence 传入模型。所有输入来源会写入会话审计。

## 数据流与边界

```text
浏览器中文界面
  -> FastAPI 路由（认证、角色校验、输入验证）
  -> 应用服务（业务授权、候选写入、任务创建）
  -> SQLite repositories
  -> Provider 平台 / 受控抓取器 / deterministic probe
```

前端仅显示有权访问的数据。后端 service 层在 repository 查询前后验证 actor、tenant 和 owner。AI 调用失败时持续复用已实现的脱敏任务持久化：界面可看见 `failed` 状态和安全错误，不能看见凭证。

## 测试与验收

每个新增 API、服务和关键前端组件先写失败测试再实现。

第一阶段验收：全局用户可见文案为中文；管理员可创建、编辑、启用、禁用普通用户；普通用户访问管理员 API 返回 403；管理员与普通用户的导航和数据范围正确。

第二阶段验收：Legado JSON 的导入/导出可 round-trip；导入不发布；跨用户候选不可导出；正则测试结果准确；bqgiu probe 明确返回 `verification_wall`，且不能发布。

第三阶段验收：用户能发起预设分析；章节、粘贴文本与允许 URL 都产生可追溯引用；非 owner 不能读会话；受控 URL 拒绝私有地址；provider 失败产生脱敏的可见 AI task。
