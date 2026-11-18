-- ============================================================
-- 012_add_phone_sms.sql · 手机号作为账号 + 短信验证码注册（lesson-39）
--
-- 干什么：
--   1) users.phone —— 手机号列。新注册老师的登录账号；存量账号留 NULL。
--   2) sms_attempts —— 短信发码/核验流水（频控 + 审计 + 投诉溯源）。
--
-- 为什么 users.username 保留不动
-- ---------------------------
-- username 是历史遗留的登录名（test1 / 共享试用账号 / 早期老师）。
-- 手机号是**新账号体系**，两件事混在一列 → 改号、改显示名、老数据回溯全乱。
-- 所以新增 phone 列，username 继续照旧；新注册用户的 username 填手机号
--（NOT NULL + UNIQUE 约束一个字都不用改）。
--
-- 依赖：001（users）、008（invites/feedbacks）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank -v ON_ERROR_STOP=1 -f migrations/012_add_phone_sms.sql
-- ============================================================

BEGIN;

-- ---------- 1. 手机号列 ----------
-- ⚠️ ADD COLUMN IF NOT EXISTS：重复执行不报错（迁移脚本要能重跑）。
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS phone VARCHAR(20);

-- 部分唯一索引：存量账号 phone 为 NULL 不受影响；
-- 手机号唯一 = 一个号只能对应一个账号（短信注册的核心约束）。
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone
    ON users (phone)
    WHERE phone IS NOT NULL;

-- ---------- 2. 短信流水表 ----------
-- ⚠️ 不存验证码明文 —— 验证码由阿里云生成并保管，核验走 CheckSmsVerifyCode。
--    这里只留「什么时候、哪个号、哪个 IP、做了什么、结果如何」，
--    够做频控，也够在有人投诉骚扰时把源头查出来。
CREATE TABLE IF NOT EXISTS sms_attempts (
    id          SERIAL PRIMARY KEY,
    -- 目标手机号
    phone       VARCHAR(20)  NOT NULL,
    -- 请求方 IP（限流 + 溯源）
    ip          VARCHAR(45)  NOT NULL DEFAULT '',
    -- send=发码 / verify=核验
    action      VARCHAR(10)  NOT NULL DEFAULT 'send',
    -- 结果（发码成功 / 核验通过）
    ok          BOOLEAN      NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 频控查询：同号 + 同动作 + 时间窗
CREATE INDEX IF NOT EXISTS ix_sms_attempts_phone_created
    ON sms_attempts (phone, created_at DESC);
-- 限流查询：同 IP + 同动作 + 时间窗
CREATE INDEX IF NOT EXISTS ix_sms_attempts_ip_created
    ON sms_attempts (ip, created_at DESC);

-- ---------- 权限 ----------
-- ⚠️ 迁移是 postgres 执行的，表默认归 postgres —— 应用账号读不了就 500。
--    所以要授权给应用账号。
--    但本地开发库里没有 teacherbank 角色（那是线上的），
--    所以这里按「角色存在才授权」写 —— 两边都能跑，不用改文件。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE sms_attempts TO teacherbank;
        GRANT ALL PRIVILEGES ON SEQUENCE sms_attempts_id_seq TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证
--   \d users
--   \d sms_attempts
--   SELECT id, username, phone FROM users ORDER BY id DESC LIMIT 10;
-- ============================================================