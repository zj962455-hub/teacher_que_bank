# 阿里云短信验证注册 · 选型与落地方案

> 评估日期：2026-11-18 · 触发：老大问「阿里云短信认证服务是不是不用额外做主体短信备案，接 SDK 就能直接用」
> 结论速览：**方向对，但老大给的两个链接只有一个适用；且「免备案」的真实代价是短信落款不能用「蓝狐网」。**

---

## 一、结论（三句话）

1. **老大的判断成立**：阿里云**短信认证服务**（号码认证服务 pnvs 下的「短信认证」原子能力）确实免签名报备、免模板报备、免短信资质审核，拿到 AccessKey 就能调 API，**不用等主体资质**。
2. **但两个链接不对应同一件事**：`VerifyMobile` 是**本机号码校验（一键登录）**，要端侧 SDK 换来的 AccessCode（电信 10 分钟 / 联通 30 分钟 / 移动 2 分钟，且仅可用一次）；我们是 Web 后台，**拿不到 AccessCode，这条路走不通**。短信验证码要用 `SendSmsVerifyCode` + `CheckSmsVerifyCode`，纯服务端 API。
3. **「免资质」不等于「免实名」**：阿里云账号要完成实名认证（个人账号即可，这条对个人开发者友好）；并且**只能用控制台赠送的签名**。

---

## 二、两个链接到底是什么

| 链接 | 实际接口 | 依赖什么 | 我们能用吗 |
|---|---|---|---|
| `Dypnsapi/VerifyMobile` | 本机号码校验（一键登录服务端核验） | 端侧 SDK 产出的 AccessCode，一次性、短时效 | ❌ Web 后台拿不到 |
| `pnvs` 短信认证新手指南 | `SendSmsVerifyCode` 发码 + `CheckSmsVerifyCode` 核验 | 只需 AccessKey（服务端调用） | ✅ 就是它 |

> 顺带：`GetMobile` 是一键登录取号（同样要端侧 SDK 授权页），也不是我们要的。

---

## 三、「不用额外做主体短信备案」——到底免了什么，代价是什么

**免掉的：**
- 短信签名报备
- 短信模板报备
- 短信平台资质审核（短信认证服务官方定位就是给个人/小团队的免资质验证码通道）

**代价（必须让老大知道）：**
- `SendSmsVerifyCode` 的 `SignName` **必填**，且官方明确「暂不支持使用自定义签名，请使用系统赠送的签名；系统赠送签名必须搭配系统赠送模板使用」
  → **老师收到的验证码短信，落款是阿里云赠送的签名，不是「蓝狐网」**。
  - ⚠️ **2026-11-18 实测修正**：老大这台账号的 DYPNS 签名配置里签名就叫「恒创联众」，
    模板编码 `100001`（**不带 `SMS_` 前缀**），配上去直接发送成功。
    所以「只能用阿里云赠送签名」这个限制在本账号上不成立 —— **落款实际是「恒创联众」**。
    结论：落款既不是「阿里云」也不是「蓝狐网」，而是「恒创联众」。
  → 理由官方也给了：运营商近期加强短信签名管控，自定义签名下发失败率高。
- 阿里云账号必须完成实名认证。

**和「通用短信服务（DMS）」的区别：**
- 短信认证服务（pnvs）：免签名模板报备，落款是赠送签名 —— 今天就能上。
- 通用短信服务（DMS）：签名可自定义成「蓝狐网」，但**要签名报备 + 模板报备 + 主体资质**（营业执照等）。
- 报备用的主体信息与公安备案要填的**是同一套**，所以不是额外成本，只是时间差。

---

## 四、实测结论（本机已跑过，不是抄文档）

| 项 | 结论 |
|---|---|
| SDK | `alibabacloud-dypnsapi20170525` 2.0.0，本机 venv 已安装、import 通过；方法名 `send_sms_verify_code` / `check_sms_verify_code` 确认存在 |
| 阿里云 pip 镜像 | `mirrors.aliyun.com/pypi/simple/alibabacloud-dypnsapi20170525/` → HTTP 200，2.0.0 wheel 在列。**服务器走阿里云镜像装包没问题**（ECS 访问海外 PyPI 会超时） |
| API 形态 | `Client.send_sms_verify_code(SendSmsVerifyCodeRequest(...))`；参数 `phone_number / sign_name / template_code / template_param / code_length / valid_time / interval / duplicate_policy / scheme_name` 全部对得上 |
| 计费 | 短信认证 API 版阶梯价：≤1000 次/月 **0.06 元/次**，之后逐档降到 0.04；**核验服务免费**；套餐包在 `dypns.console.aliyun.com/package` |
| **关键约束** | `TemplateParam` 必须传 `{"code":"##code##","min":"5"}` 让**阿里云动态生成**验证码；自己传固定码，阿里云**无法核验**（`CheckSmsVerifyCode` 会一直 UNKNOWN）→ 服务端不必落库明文码 |
| 常见错误码 | `isv.PRODUCT_UNSUBSCRIBE` 未开通 / `isv.RAM_PERMISSION_DENY` RAM 没授权 / `isv.OUT_OF_SERVICE` 欠费 / `isv.MOBILE_NUMBER_ILLEGAL` 号码非法 |

---

## 五、和公安备案的关系（别混淆）

- **两件事互不阻塞**：公安联网备案是网站本身的行政手续（beian.mps.gov.cn，2026-12-02 截止）；短信服务是登录方式。谁也不挡谁。
- **好消息**：短信认证免资质 → `docs/decisions.md` 里「阶段 2 手机号+验证码 = 需等公安备案成功才能做」这个前提**不成立了**，短信注册可以**现在就做**，不必等 12-02。
- **该交还得交**：备案的「主办单位 / 负责人 / 安全负责人」信息是一套两处用 —— 公安备案要用，将来通用短信服务的自有签名报备也要用。

---

## 六、落地清单（按真实代码结构）

| 文件 | 改动 |
|---|---|
| `backend/app/migrations/012_add_phone_sms.sql`（新） | `users` 加 `phone`；新建 `sms_send_log`（频控 + 审计） |
| `backend/app/services/sms.py`（新） | 封装 SDK；读 `ALIYUN_SMS_AK/SK/SIGN_NAME/TEMPLATE_CODE/SCHEME_NAME`；`send_code` / `check_code`；异常映射成项目统一错误码 |
| `backend/app/routers/auth.py` | 新增 `POST /api/auth/sms/send`（免登录）；注册请求体改为手机号/验证码（**核验合进注册接口**，见下方「与初版方案的两处偏离」） |
| `backend/app/services/errors.py` | 加 `CODE_SMS_SEND_FAILED` / `CODE_SMS_CODE_INVALID` / `CODE_SMS_RATE_LIMITED` |
| `frontend/src/api/auth.js` | `sendSmsCode` / `checkSmsCode` |
| `frontend/src/components/LoginPanel.vue` | 注册页加手机号 + 验证码 + 倒计时按钮 + 「同意接收短信」勾选 |
| `deploy/teacher-bank/01-install.sh` | pip install 加 `alibabacloud-dypnsapi20170525` |
| `/etc/teacherbank/app.env` | 加 `ALIYUN_SMS_*`（chmod 600，不入 git） |

---

## 七、三件不能省的事

1. **频控**。项目现在**没有任何限流中间件**（`services/invites.py` 只是靠熵）。短信发送接口必须自己做 IP + 手机号双维度限流（建议 60 秒 1 次、每日上限），否则 0.06 元/次会被刷爆，还会触发阿里云风控与运营商投诉。
2. **开通与取号**（老大在控制台做，本机无阿里云凭据）：
   - `dypns.console.aliyun.com/functions` 开通「短信认证」
   - `dypns.console.aliyun.com/smsCertParamsConfig/sign` 选赠送签名 → 拿 `SignName`
   - `dypns.console.aliyun.com/smsCertParamsConfig/template` 选赠送模板 → 拿 `TemplateCode`
   - 建 RAM 子账号 AK，只授 `dypns:SendSmsVerifyCode` + `dypns:CheckSmsVerifyCode`
3. **合规与隐私**：注册页明示同意接收短信；日志不打明文验证码；手机号属个人信息，按最小必要收集（只做校验、不落库最省事）。

---

## 八、待老大拍板

- **落款**：先用赠送签名（今天能上，落款不是「蓝狐网」），还是等主体信息齐了换通用短信服务的自有签名？
- **范围**：短信注册是**替代**现有邀请码注册，还是与邀请码**并存**？（现在是邀请码自助注册：`POST /api/auth/register`）
- **凭据**：AK 老大开好后直接给我，还是我把代码写完、老大自己填进 `/etc/teacherbank/app.env`？

---

## 九、工作量估计

后端约 200 行 + 1 个迁移 + 前端 1 个组件改动 + 1 个依赖 + 3 个环境变量；含本机测试 1 轮、线上部署 1 轮，**约 1 个工作日**。

## 十、与初版方案的偏离（2026-11-18 落地后修正）

### 1. 不做独立的 `/auth/sms/check`，核验合进注册接口

初版方案写的是「`/sms/send` 发码 + `/sms/check` 核验」两个接口。落地时改成**注册接口内部直接核验**：

- 少一次网络往返（老师点「注册」只等一次）
- 验证码用完即焚（核验成功后阿里云侧即失效，不存在「核验过但没注册」的悬空态）
- 少一个可被滥用的公开端点

代价：前端拿不到「验证码正确但密码不合规」这种中间态反馈 —— 现在的做法是**后端先验密码强度再核验验证码**，弱密码不会白费验证码。

### 2. 加了 `REGISTRATION_ENABLED` 总开关

短信注册把邀请码那道闸拆了 —— 任何能收短信的号都能注册。
所以留了一个环境变量，`REGISTRATION_ENABLED=false` 一键关注册（发码与注册都返回 403 `auth.registration_closed`）。

### 3. 登录框不限 11 位

手机号是 11 位，但**存量账号**的用户名可能是「张老师」这种长串 —— 限 11 位会让老老师登不进去，所以输入框放开到 50 位。
