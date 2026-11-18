-- ============================================================
-- 015_add_login_attempts.sql · 登录尝试流水（lesson-42 · 公安备案 · 个人信息保护）
--
-- 干什么：
--   新增 login_attempts 表 —— 记每一次登录尝试（成功与失败都记）。
--   用途：① 登录限流，防撞库（仓库里一直缺全局限流）；
--         ② 审计：事后可查「谁在何时从哪个 IP 试过哪个账号」。
--
-- 只记结果与元信息，**不记密码**。
--
-- 执行：
--   cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f 015_add_login_attempts.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS login_attempts (
    id         SERIAL PRIMARY KEY,
    account    VARCHAR(50) NOT NULL DEFAULT '',
    ip         VARCHAR(45) NOT NULL DEFAULT '',
    ok         BOOLEAN      NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_login_attempts_ip_created
    ON login_attempts (ip, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_login_attempts_account_created
    ON login_attempts (account, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_login_attempts_ok_created
    ON login_attempts (ok, created_at DESC);

-- ---------- 权限 ----------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE login_attempts TO teacherbank;
        GRANT ALL PRIVILEGES ON SEQUENCE login_attempts_id_seq TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证：
--   SELECT created_at, account, ip, ok FROM login_attempts ORDER BY id DESC LIMIT 10;
-- ============================================================
