-- ============================================================
-- 002_add_sessions.sql · 登录会话表（lesson-11）
--
-- 依赖：001_add_users.sql 已执行（users 表存在）
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/002_add_sessions.sql
-- ============================================================

BEGIN;

-- ---------- 1. 建 sessions 表 ----------
CREATE TABLE IF NOT EXISTS sessions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER        NOT NULL REFERENCES users (id),
    token_hash    VARCHAR(64)    NOT NULL UNIQUE,
    expires_at    TIMESTAMPTZ    NOT NULL,
    last_used_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    ip            VARCHAR(45)    NOT NULL DEFAULT '',
    user_agent    VARCHAR(300)   NOT NULL DEFAULT ''
);

-- 查「某用户的活跃会话」用 user_id + expires_at
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id);
-- 查「这个 token 是否还有效」用 token_hash（UNIQUE 约束自带索引）
-- 定期清理过期会话用 expires_at
CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions (expires_at);

COMMIT;

-- ============================================================
-- 验证
--   \d sessions
-- ============================================================
