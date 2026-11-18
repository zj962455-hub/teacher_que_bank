-- ============================================================
-- 014_add_audit_logs.sql · 操作审计日志（lesson-41 · 公安备案安全评估）
--
-- 干什么：
--   新增 audit_logs 表 —— 一条 = 一次 API 操作，记齐安全评估要求的字段：
--   用户账号 / 操作时间 / 操作类型 / 网络源地址 / 目标地址 / 网络源端口 / 客户端硬件特征。
--
-- 为什么 nginx 的 access.log 不够：
--   nginx 记的是「哪个 IP 访问了哪个 URL」，不知道访问的是哪个登录用户；
--   审计要能按账号检索，所以应用层自己记一份。
--
-- 执行：
--   cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f 014_add_audit_logs.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS audit_logs (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER,
    username     VARCHAR(50)  NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    method       VARCHAR(10)  NOT NULL DEFAULT '',
    path         VARCHAR(300) NOT NULL DEFAULT '',
    action       VARCHAR(300) NOT NULL DEFAULT '',
    client_ip    VARCHAR(45)  NOT NULL DEFAULT '',
    client_port  VARCHAR(10)  NOT NULL DEFAULT '',
    target_host  VARCHAR(120) NOT NULL DEFAULT '',
    target_path  VARCHAR(300) NOT NULL DEFAULT '',
    user_agent   VARCHAR(300) NOT NULL DEFAULT '',
    status_code  INTEGER      NOT NULL DEFAULT 0,
    duration_ms  INTEGER      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_user_created
    ON audit_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created
    ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_logs_client_ip
    ON audit_logs (client_ip, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action
    ON audit_logs (action, created_at DESC);

-- ---------- 权限 ----------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE audit_logs TO teacherbank;
        GRANT ALL PRIVILEGES ON SEQUENCE audit_logs_id_seq TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证：查表结构，再看最近几条
--   SELECT created_at, username, action, client_ip, client_port,
--          target_host, status_code FROM audit_logs ORDER BY id DESC LIMIT 5;
-- ============================================================
