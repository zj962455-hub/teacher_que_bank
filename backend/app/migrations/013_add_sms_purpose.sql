-- ============================================================
-- 013_add_sms_purpose.sql · 验证码用途（lesson-40 · 忘记密码重置）
--
-- 干什么：
--   sms_attempts 加 purpose 列 —— 记录这次发码是「注册」还是「重置密码」。
--
-- 为什么需要
-- ------------
-- 阿里云那边验证码只认手机号，**不认用途** —— 同一个号发的码，
-- 在阿里云看来是没区别的。要做用途隔离（注册用的码不许拿去改密码），
-- 就只能在我们自己这边记一笔：发码时记用途，核验时对一下。
--
-- 老数据的 purpose 默认 register —— 与它们当时的实际用途一致。
--
-- 执行：
--   cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f 013_add_sms_purpose.sql
-- ============================================================

BEGIN;

-- 重复执行不报错（迁移脚本要能重跑）
ALTER TABLE sms_attempts
    ADD COLUMN IF NOT EXISTS purpose VARCHAR(16) NOT NULL DEFAULT 'register';

-- 核验时按「手机号 + 用途」找最近一次发码 —— 加个联合索引
CREATE INDEX IF NOT EXISTS ix_sms_attempts_phone_purpose
    ON sms_attempts (phone, purpose, created_at DESC);

-- ---------- 权限 ----------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE sms_attempts TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证：查表结构，再看最近几条流水
--   SELECT phone, action, purpose, ok, created_at FROM sms_attempts ORDER BY id DESC LIMIT 5;
-- ============================================================
