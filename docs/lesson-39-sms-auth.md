# lesson-39 · 手机号作为账号 + 短信验证码注册

> 老大 2026-11-18 10:44 拍板：①落款用阿里云赠送签名 ②短信注册**替代**邀请码注册，手机号当账号 ③代码写完他手动填 AK。

---

## 一、这一课改了什么

| 原来（lesson-34 邀请码时代） | 现在（lesson-39） |
|---|---|
| 登录用**用户名** | 登录用**手机号**（存量账号仍可用原用户名） |
| 注册要**邀请码** | 注册要**短信验证码** |
| 老师得记一个用户名 | 老师只记手机号 |
| 邀请码是注册闸门 | 闸门拆了 → 留 `REGISTRATION_ENABLED` 总开关兜底 |

---

## 二、用的阿里云产品

**短信认证服务**（号码认证服务 pnvs 下的「短信认证」原子能力），不是通用短信服务（DMS）。

| | 短信认证服务（本次用的） | 通用短信服务 DMS |
|---|---|---|
| 签名/模板报备 | **免**（用赠送签名 + 赠送模板） | 要报备 |
| 资质审核 | 免 | 要 |
| 落款 | 平台赠送签名（不是「蓝狐网」） | 可自定义 |
| 计费 | 0.06 元/条起（核验免费），阶梯降价 | 另算 |
| 开通 | 控制台开一下 + AccessKey | 同 |

---

## 三、验证码为什么我们不存

发码时 `TemplateParam` 传：

    {"code": "##code##", "min": "5"}

`##code##` 是占位符 —— **验证码由阿里云生成并保管**。我们全程不知道明文码，
核验时调 `CheckSmsVerifyCode` 让阿里云比对它自己存的那份。

所以本地库里只有「给哪个号发过、结果如何」，**没有验证码可偷**。
数据库被拖走也换不来一个号。

⚠️ 代价：核验必须走一次网络往返（本来就是网络场景，可接受）。

---

## 四、接口契约

### POST /api/auth/sms/send（免登录）

    { "phone": "13800138000" }
    → 200 { "sent": true, "cooldown": 60 }

### POST /api/auth/register（免登录）

    { "phone": "13800138000", "code": "123456", "password": "...", "display_name": "张老师" }
    → 200 { "token": "...", "user": { "username": "13800138000", ... } }

注册成功**直接签发会话** —— 老师填完表就进首页，不用再登一次。

### POST /api/auth/login

    { "account": "13800138000", "password": "..." }

`account` 传手机号；后端也会兜底查旧用户名，所以存量账号（test1 之类）照常能登。
旧前端传 `username` 字段也仍然有效。

---

## 五、错误码

| code | 老师该做什么 |
|---|---|
| `sms.not_configured` | 找管理员（服务端没配 AK） |
| `sms.rate_limited` | 等一会儿再试 |
| `sms.send_failed` | 换个网络/稍后再试 |
| `sms.code_invalid` | 重新输一遍验证码 |
| `auth.account_not_found` | 手机号还没注册 → 前端引导去注册 |
| `auth.invalid_credentials` | 密码错了，重输 |
| `auth.phone_taken` | 该号已注册，直接登录 |
| `auth.registration_closed` | 注册通道被关了，找管理员 |

---

## 六、频控（自己实现的，全项目原本没有任何限流）

| 维度 | 阈值 |
|---|---|
| 同手机号重发间隔 | 60 秒 |
| 同手机号每天 | 10 条 |
| 同 IP 每小时 | 20 条 |
| 同 IP 每天 | 100 条 |
| 同号核验失败每小时 | 10 次（防穷举 6 位码） |

频控拦在**阿里云之前** —— 一次都别多花。

---

## 七、文件清单

| 文件 | 作用 |
|---|---|
| `backend/app/migrations/012_add_phone_sms.sql` | users.phone 列 + sms_attempts 表 |
| `backend/app/models.py` | User.phone 字段 + SmsAttempt 模型 |
| `backend/app/services/sms.py` | 发送/核验/频控/错误映射 |
| `backend/app/services/errors.py` | 新机器码 |
| `backend/app/routers/auth.py` | /sms/send + 短信注册 + 手机号登录 |
| `frontend/src/api/auth.js` | sendSmsCode + register/login 新契约 |
| `frontend/src/components/LoginPanel.vue` | 手机号登录 + 验证码注册（倒计时） |
| `backend/tests/test_sms.py` | 短信流程 19 条用例 |
| `deploy/teacher-bank/deploy-lesson39.sh` | 一键部署（含迁移 + SDK 安装） |
| `deploy/teacher-bank/app.env.sms.example` | 短信环境变量模板（老大手动填） |
| `deploy/teacher-bank/ram-policy.sms.json` | RAM 自定义策略（只授两个 dypns action） |
| `deploy/teacher-bank/sms-smoke-test.py` | 独立冒烟测试：不连库直接调 SDK，分清权限/签名/模板/产品开通 |

---

## 八、老大手动填的东西

服务器 `/etc/teacherbank/app.env`（chmod 600，不入 git）：

    ALIYUN_SMS_ACCESS_KEY_ID=...
    ALIYUN_SMS_ACCESS_KEY_SECRET=...
    ALIYUN_SMS_SIGN_NAME=<控制台赠送签名>
    ALIYUN_SMS_TEMPLATE_CODE=<控制台赠送模板CODE>

填完 `systemctl restart teacherbank-api` 即生效。

控制台要做的：开通「短信认证」→ 选赠送签名 → 选赠送模板 → 建只授两个 dypns 权限的 RAM 子账号。

### 8.1 建 RAM 用户（2026-11-18 老大确认按此方案）

**为什么用 RAM 用户而不是主账号 AK**：主账号 AK 是账号的「万能钥匙」，能删 OSS、改 RAM、动账单。
应用一旦持有它，泄露等于整个阿里云账号被接管。RAM 用户 + 最小权限，泄露的爆炸半径只剩「发短信」。

控制台操作（RAM 控制台 → 用户 → 创建用户）：

1. 登录名随便起，比如 `teacherbank-sms`
2. **访问方式只勾「OpenAPI 调用访问」，不要勾控制台登录**
3. 创建后进「AccessKey」页签 → 创建 AccessKey → **把 ID/Secret 存下来**（Secret 只显示一次）
4. 「权限管理」→ 新增授权 → 自定义策略 → 粘贴下面的 JSON

自定义策略（也在 `deploy/teacher-bank/ram-policy.sms.json`，可直接导入）：

    {
      "Version": "1",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["dypns:SendSmsVerifyCode", "dypns:CheckSmsVerifyCode"],
          "Resource": "*"
        }
      ]
    }

> 号码认证服务是全局资源、不分地域，所以 `Resource` 只能是 `*`。
> **不要**图省事挂 `AliyunFullAccess` 或 `AliyunDMSFullAccess`。

### 8.2 填值 + 自测（不用先重启服务）

AK/SK 只写服务器 `/etc/teacherbank/app.env`（chmod 600），不要发到群里、不要进仓库。

填完先自测一次，把「权限 / 签名 / 模板 / 产品是否开通」四种失败一次分清：

    # 1. 发一条
    /opt/teacher-bank/.venv/bin/python deploy/teacher-bank/sms-smoke-test.py send 13800138000

    # 2. 拿收到的验证码核验
    /opt/teacher-bank/.venv/bin/python deploy/teacher-bank/sms-smoke-test.py check 13800138000 123456

自测通过再重启服务：

    systemctl restart teacherbank-api

### 8.3 更稳的做法：ECS RAM 角色（可以后做）

服务器上的静态 AK/SK 仍然是「长期有效的静态凭据」。如果这台机器是 ECS 或轻量应用服务器，
可以给实例绑一个 RAM 角色，让 SDK 自动取 STS 临时凭据 —— **服务器上根本不存 AK/SK**。

代价：`backend/app/services/sms.py` 现在是硬编码 `Config(access_key_id=..., access_key_secret=...)`，
要走角色得改成用 `alibabacloud_credentials` 的默认凭据链（约 15 行）。
可以做成双模：env 里有 AK 就用 AK，没有就自动走凭据链，这样两条路都通、将来切角色不用再改代码。

---

## 九、还留着的两件事

1. **邀请码管理接口仍在**（`/api/auth/invites`）—— 管理员还能生成/停用码，但**不再参与注册**。
2. **`REGISTRATION_ENABLED=false`** —— 邀请码时代的闸被短信注册拆了，这个环境变量是一键关注册的保险。