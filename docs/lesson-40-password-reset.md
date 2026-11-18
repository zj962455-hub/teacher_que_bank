# lesson-40 · 手机号验证码重置密码（老师忘记密码）

> 老大 2026-11-18 16:41 提的需求：「老师注册后忘记自己的密码，要支持通过手机号验证码修改新密码」。

## 一、这一课改了什么

| 位置 | 改动 |
|---|---|
| `backend/app/models/account.py` | `SmsAttempt` 加 `purpose` 字段（register / reset） |
| `backend/app/migrations/013_add_sms_purpose.sql` | `sms_attempts` 加 `purpose` 列 + 联合索引 |
| `backend/app/services/sms.py` | 发码/核验带用途；核验时**核对用途**，对不上就拒 |
| `backend/app/routers/auth.py` | `sms/send` 支持 `purpose`；新增 `POST /api/auth/password/reset` |
| `frontend/src/api/auth.js` | `sendSmsCode(phone, purpose)`；新增 `resetPassword()` |
| `frontend/src/components/LoginPanel.vue` | 第三个页签「忘记密码」 |
| `backend/tests/test_password_reset.py` | 13 条新用例 |

## 二、接口契约

### POST /api/auth/sms/send（免登录）

请求：

    { "phone": "13800138000", "purpose": "reset" }

- `purpose`：`register`（默认）/ `reset`。不传按注册算（老前端不受影响）。
- `purpose=reset` **只对已注册的号发** —— 没注册的号 → 404 `auth.account_not_found`。
- 别的用途 → 400 `request.validation_failed`。

响应：`{ "sent": true, "cooldown": 60 }`

### POST /api/auth/password/reset（免登录）

请求：

    { "phone": "13800138000", "code": "123456", "new_password": "..." }

流程：查号 → 验新密码强度 → 阿里云核验验证码 → 改密码 → **踢掉所有旧会话** → 签发新会话。

响应（跟登录同构）：

    { "token": "...", "token_type": "bearer", "expires_in_days": 7, "user": { ... } }

| 情况 | 状态码 | 机器码 | 文案 |
|---|---|---|---|
| 号没注册 | 404 | `auth.account_not_found` | 这个手机号还没注册过，没有密码可以重置 |
| 共享试用账号 | 403 | `auth.password_change_locked` | 该账号是共享试用账号，需要改请联系管理员 |
| 新密码弱 | 400 | `request.validation_failed` | 新密码不合规：至少一个大写字母 |
| 验证码不对 | 400 | `sms.code_invalid` | 验证码不对或已过期，重新输一下 |
| **用途不符** | 400 | `sms.code_invalid` | 这是注册用的验证码，不能用来重置密码，请重新获取 |

## 三、为什么要有「用途」这一层

阿里云那边验证码只认手机号，**不认用途** —— 同一个号发的码，在阿里云看来没区别。
所以用途隔离只能在我们自己这边做：发码时把用途记进 `sms_attempts.purpose`，核验时对一下。

**不留这个口子会怎样**：老师自己申请了一个「注册」验证码。那个码要是也能拿去重置密码，
就多了一条「不用输入旧密码就能改密」的路径 —— 虽然都得先拿到那个号，但没必要。

## 四、安全考量

1. **改完踢掉所有旧会话**（不像「修改密码」只踢其他设备）：忘密码的场景下不能排除是别人拿着手机改了密码，旧会话必须全清。
2. **共享试用账号不给自助改密**：`allow_password_change=false` 的账号直接 403 —— 改一个所有人掉线。
3. **弱密码在核验验证码之前就拒**：别白烧一次核验机会（核验失败有每小时上限）。
4. **库里不存验证码明文**：老规矩，重置路径也得守 —— 验证码由阿里云生成并保管。
5. **频控共用一份预算**：注册和改密的倒计时是同一个 —— 别让切用途绕过频控（0.06 元/条，刷起来是真金白银）。

## 五、怎么用（老师视角）

登录页 → 第三个页签「忘记密码」→ 填注册手机号 → 获取验证码 → 填码 + 新密码 → 「重置密码并进入」。

重置完自动登录，其他设备的登录状态全部失效。

## 六、验收

- 后端全量：**321 passed, 3 warnings in 87.53s**，退出码 0（基线 304 + 新增 17 条）。
- 新增 13 条用例（`backend/tests/test_password_reset.py`）：用途记录、用途隔离、reset 只对已注册号发、
  弱密码先拒、错码不改密、成功改密并自动登录、旧会话全失效、共享账号 403、不存明文。
- 前端构建 ✅ 342ms。
- 线上：迁移 013 已执行（`purpose` 列存在）→ 部署退出码 0 → 新路由 404/422 正常 →
  `purpose=reset` 真发短信 200 → 流水 `136****6247|send|reset|t` → 服务 active、站点 200。