# 后端测试契约迁移（第四批）设计

## 目标

将 `test_core_security.py` 从已删除或已经改变的安全辅助函数约定迁移到当前
`app.core.security` 的公开行为。

## 根因

测试仍假设：

- API key 固定为 35 字符；
- access token 支持调用方自定义 `expires_delta`；
- 无效/过期 access token 解码为 `None`；
- 模块提供 `mask_api_key()`；
- 密码散列是固定 64 字符 SHA-256。

当前实现明确采用 `secrets.token_urlsafe(32)`、配置驱动的 access-token 过期
时间、无效 token 返回空字典，以及 bcrypt 密码散列。`mask_api_key()` 没有
当前调用方，也不是公开安全模块契约。

## 方案

只迁移测试，不改变生产安全语义：

- API key 测试验证 `lh_` 前缀、非空 url-safe 随机负载和多次生成唯一性；
- access token 测试验证保留业务 claim、标准 `aud=access` 和配置驱动的
  `exp`，不再传递已移除的 `expires_delta`；
- 无效 token 测试断言空字典；
- 删除 `mask_api_key()` 的旧测试；
- bcrypt 测试验证 `$2` 格式、非明文、每次随机盐生成不同散列，并继续用
  `verify_password()` 验证兼容性。

## 非目标

- 不恢复 `mask_api_key()` 或自定义过期参数。
- 不把 bcrypt 改回 SHA-256。
- 不改变 JWT 发行、刷新 token 或身份依赖实现。

## 验收

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q tests\test_core_security.py tests\test_core_security_main.py --tb=short
```

提交前还必须执行：

```powershell
git diff --check
```
