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
| `backend/scripts/sms_smoke_test.py` | 独立冒烟测试：不连库直接调 SDK，分清权限/签名/模板/产品开通（rebuild.sh 会自动同步到服务器 `/opt/teacher-bank/app/scripts/`） |

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
    /opt/teacher-bank/.venv/bin/python /opt/teacher-bank/app/scripts/sms_smoke_test.py send 13800138000

    # 2. 拿收到的验证码核验
    /opt/teacher-bank/.venv/bin/python /opt/teacher-bank/app/scripts/sms_smoke_test.py check 13800138000 123456

自测通过再重启服务：

    systemctl restart teacherbank-api

### 8.3 凭据方案：默认走 ECS 实例 RAM 角色（STS 临时凭据）

线上这台是阿里云 ECS（`i-0jldm8ubd3nmhp5b5e8tZ` / `cn-wulanchabu` / `ecs.e-c1m2.large`）。
代码已改成**双模**（`backend/app/services/sms.py`）：

| 来源 | 条件 | 服务器上存不存密钥 |
|---|---|---|
| `env-ak` | `app.env` 里填了 `ALIYUN_SMS_ACCESS_KEY_ID` + `_SECRET` | 存（长期有效的静态凭据） |
| `ecs-ram-role` | 没填 AK → 自动向实例元数据服务取 STS 临时凭据 | **不存** |

走角色时 STS 令牌由元数据服务（100.100.100.200）发放，SDK 在令牌过期时**自动续期**
（`EcsRamRoleCredential` 继承 `_AutomaticallyRefreshCredentials`），长期运行不用管。

**没有凭据时的报错**：`短信服务凭据没配好，请联系管理员`（机器码 `sms.not_configured`），不是 500。

#### 控制台配置（六步）

**第 1 步 · 创建 RAM 角色**

RAM 控制台 → 身份管理 → 角色 → 创建角色

- 角色名称：`TeacherBankSmsRole`
- 受信实体类型：**云服务**
- 受信服务：**ECS（云服务器）**
- 信任策略（控制台自动生成，确认是这段）：

      {
        "Version": "1",
        "Statement": [
          {
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
              "Service": ["ecs.aliyuncs.com"]
            }
          }
        ]
      }

**第 2 步 · 给角色授最小权限**

RAM 控制台 → 身份管理 → 策略 → 创建自定义策略 → 粘贴 `deploy/teacher-bank/ram-policy.sms.json` 的内容 → 命名 `TeacherBankSmsPolicy`。

再回到角色详情 → 权限管理 → 新增授权 → 选 `TeacherBankSmsPolicy`。

**第 3 步 · 绑到 ECS 实例**

ECS 控制台 → 实例与镜像 → 实例 → 找到 `i-0jldm8ubd3nmhp5b5e8tZ`（杭州 cn-wulanchabu）
→ 更多 → **实例 RAM 角色** → 选 `TeacherBankSmsRole` → 确认。

> ⚠️ **这一步需要重启实例才生效** —— 阿里云要求给已有实例绑定实例 RAM 角色后重启，
> 元数据服务才会开始发放角色凭据。
>
> 重启风险已核实（2026-11-18）：`teacherbank-api` / `paddleocr-api` / `nginx` / `postgresql`
> 全是 `active=enabled`，重启后会自动拉起，站点停机约 1~2 分钟。

**第 4 步 · 验证角色已生效**

    ssh root@8.160.177.222
    curl -s http://100.100.100.200/latest/meta-data/ram/security-credentials/
    # 应该输出：TeacherBankSmsRole

**第 5 步 · 填签名和模板（AK 两行不用填）**

    sudo vi /etc/teacherbank/app.env
    # 追加两行：
    ALIYUN_SMS_SIGN_NAME=<赠送签名的 SignName>
    ALIYUN_SMS_TEMPLATE_CODE=<赠送模板的 TemplateCode>

    sudo chown teacherbank:teacherbank /etc/teacherbank/app.env
    sudo chmod 600 /etc/teacherbank/app.env
    sudo systemctl restart teacherbank-api

**第 6 步 · 自测发一条**

    /opt/teacher-bank/.venv/bin/python /opt/teacher-bank/app/scripts/sms_smoke_test.py send 13800138000

看到 `[cred] 凭据来源: ecs-ram-role` 且「✅ 发送成功」就说明整条链路通了。

#### 不想重启的话：退回静态 AK

跳过第 3 步，改成建 RAM 子账号（只授 `ram-policy.sms.json` 那两个 action），
把 AK/SK 填进 `app.env` 的 `ALIYUN_SMS_ACCESS_KEY_ID` / `ALIYUN_SMS_ACCESS_KEY_SECRET`。
代码不用改 —— 检测到 env 有 AK 就走 AK，没有才走角色。

---

## 九、还留着的两件事

1. **邀请码管理接口仍在**（`/api/auth/invites`）—— 管理员还能生成/停用码，但**不再参与注册**。
2. **`REGISTRATION_ENABLED=false`** —— 邀请码时代的闸被短信注册拆了，这个环境变量是一键关注册的保险。