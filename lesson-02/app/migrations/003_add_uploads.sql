-- ============================================================
-- 003_add_uploads.sql · 上传图片归属表（lesson-11）
--
-- 为什么需要这张表：
--   之前 questions.image_path 只存路径字符串，**读图片时无法判断归属**。
--   这张表建立「文件名 → user_id」的映射，读图片时校验。
--
-- 依赖：001（users）、002（sessions）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/003_add_uploads.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS uploads (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER        NOT NULL REFERENCES users (id),
    filename       VARCHAR(255)  NOT NULL UNIQUE,
    url            VARCHAR(500)  NOT NULL,
    original_name  VARCHAR(255)  NOT NULL DEFAULT '',
    size           INTEGER       NOT NULL DEFAULT 0,
    content_type   VARCHAR(100)  NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_uploads_user_id ON uploads (user_id);
CREATE INDEX IF NOT EXISTS ix_uploads_filename ON uploads (filename);

COMMIT;

-- ============================================================
-- 验证
--   \d uploads
-- ============================================================
