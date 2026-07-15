# 交互式浏览器验证运行手册

## 用途与边界

交互式浏览器验证用于书源候选在普通 HTTP 探测遇到验证页时，提供一次受控的、人工可继续的浏览器会话。它不是书源审核的替代品：无论自动还是人工流程，书源都必须在同一个浏览器上下文中完成 `search`、`toc`、`content` 三段验证，才会回到正常候选/审核路径。

该能力默认关闭。关闭、运行环境缺失、容量已满或会话异常时，系统返回能力不可用（例如 `browser_unavailable`），不会把候选直接视为通过，也不会绕过既有审核。

浏览器仅以普通 Chromium 运行，不包含任何对抗性验证绕过能力。自动探测会检查跨来源导航；用于书源 `search`、`toc`、`content` 验证的 `BrowserHttpClient` 请求限定为该书源的来源 origin。人工 VNC 画面本身不会对地址栏导航实施额外的技术限制，操作者必须只访问已获授权的目标来源。

本能力明确禁止以下行为，不能通过配置、插件或运维脚本启用：

- CAPTCHA solver、打码平台或任何自动验证码求解；
- 代理、代理池或代理轮换；
- stealth 模式、反检测补丁或浏览器自动化伪装；
- 指纹伪造（包括 UA、Canvas、WebGL、时区、语言或设备指纹伪造）；
- Cookie 导出、下载、展示、转存或复用于其他会话。

系统不持久化 Cookie、浏览器 profile、页面 HTML、截图或凭据。临时 profile 仅在会话进程存活期间使用，关闭时会删除。

## 管理员设置

具有系统设置管理权限的管理员可在 **System Settings → Interactive Browser Verification** 配置并保存以下项目：

| 设置 | 默认值 | 有效范围/作用 |
| --- | --- | --- |
| Enable interactive browser verification | `false` | 总开关；关闭后不创建浏览器会话。 |
| Automatic attempt | `true` | 开启时先由普通 Chromium 自动尝试一次；仍需验证时才提供人工会话。关闭时仍启动普通 Chromium 人工会话，但不执行自动页面探测。 |
| Max concurrent sessions | `1` | `1`–`3`；达到上限时返回能力不可用。 |
| Session timeout | `300` 秒 | `60`–`600` 秒；会话到期后不可继续。 |

服务端也提供受同一管理员权限保护的设置接口：

- `GET /api/system/interactive-browser-settings`
- `PUT /api/system/interactive-browser-settings`

请在正式启用前确认实际运行环境具备下述依赖。设置保存成功不代表运行时依赖已经就绪。

## 自动与人工流程

1. 常规书源全链探测发现验证页后，系统创建受所有者绑定的候选会话。
2. 若启用自动尝试，系统以普通 Chromium 打开书源来源并检查页面；自动通过后，仍以该浏览器上下文执行 `search`、`toc`、`content` 全链验证。
3. 自动验证页未解除时，候选状态为 `awaiting_manual_verification`。具有 `engine.test` 权限且属于该会话所有者的用户可在书源构建页面打开人工验证面板。
4. 人工完成页面操作后点击继续。系统再次在同一浏览器上下文执行 `search`、`toc`、`content`。只有三段全部通过且正文长度符合校验，候选才进入正常通过/审核流程；否则继续等待人工处理或标记为失败。

取消、成功、失败或到期都会终止浏览器相关进程并删除临时 profile。默认会话时长为 300 秒；不要把人工验证窗口当作长期远程浏览器使用。

## 部署依赖

运行节点必须安装并可执行以下组件：

- Chromium
- Xvfb
- x11vnc
- websockify
- Playwright Python 包（与后端依赖版本一致）

项目 Docker 镜像已安装 Chromium、Xvfb、x11vnc 与 websockify，后端依赖层包含 Playwright Python 包；非 Docker 部署需要由运维人员安装这些运行时，并让后端进程能在 `PATH` 中找到它们。缺少任一组件时，系统应保持能力不可用，不应通过修改审核结果来替代人工验证。

## 网络与访问控制

图形显示、VNC、Chromium 调试端口和 websockify 都只能监听 `127.0.0.1`。前端不接收原始端口、浏览器调试端点或浏览器存储数据。

前端使用 Hub 的 WebSocket relay 访问人工会话。relay 具有以下边界：

- 浏览器会话相关 REST 操作要求已登录用户并具备 `engine.test` 权限；系统设置接口使用系统设置管理权限。
- 会话、取消、继续验证和 relay ticket 都按 owner scope 校验；其他用户不能访问该会话。
- WebSocket `Origin` 必须命中后端 `ALLOWED_ORIGINS`。
- relay ticket 是由 owner-authorised REST 铸造的一次性 bearer，随会话到期且消费后即失效。WebSocket relay 本身不再独立执行登录态认证，而是校验 `Origin`、owner ID 和该一次性 ticket。

部署时，请把实际 Hub 前端的所有访问 origin 写入 `ALLOWED_ORIGINS`，包括协议、域名和端口（如有）。否则浏览器面板的 WebSocket relay 会被拒绝。不要为方便调试而将 VNC、websockify 或 Chromium 调试端口暴露到公网。

## 运行与排障

- 建议先保持总开关关闭，确认依赖、`ALLOWED_ORIGINS` 与登录权限后，再在 System Settings 中启用。
- 如果界面显示能力不可用，检查 Chromium、Xvfb、x11vnc、websockify 和 Playwright 是否可用，以及并发会话是否已达到上限；不要将失败候选手工标记为已通过。
- 如果 relay 无法连接，检查 Hub 前端实际 Origin 是否已加入 `ALLOWED_ORIGINS`，以及后端是否运行在更新后的镜像/依赖环境中。
- 运行和调试日志不得打印 relay token、Cookie、会话存储或其他认证数据。反向代理和访问日志也必须排除或脱敏 relay WebSocket 的 query string，因为其中含一次性 ticket。排障时仅记录会话 ID、状态、阶段结果和无敏感信息的失败原因。
