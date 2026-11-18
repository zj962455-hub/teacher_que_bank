-- ============================================================
-- 005_add_tags.sql · 标签系统（lesson-11）
--
-- 标签和分类树的区别：
--   categories  层级结构，一题只能属于一个分类
--   tags        扁平结构，一题可以打多个标签
--
-- 依赖：001（users）、004（categories）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/005_add_tags.sql
-- ============================================================

BEGIN;

-- ---------- 1. 标签表 ----------
CREATE TABLE IF NOT EXISTS tags (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER      NOT NULL REFERENCES users (id),
    name       VARCHAR(30)  NOT NULL,
    color      VARCHAR(10)  NOT NULL DEFAULT '#18a058',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tags_user_id ON tags (user_id);

-- ---------- 2. 题目 ↔ 标签 关联表 ----------
CREATE TABLE IF NOT EXISTS question_tags (
    id          SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions (id),
    tag_id      INTEGER NOT NULL REFERENCES tags (id)
);

CREATE INDEX IF NOT EXISTS ix_question_tags_question_id ON question_tags (question_id);
CREATE INDEX IF NOT EXISTS ix_question_tags_tag_id ON question_tags (tag_id);

-- 同一对关系不重复
CREATE UNIQUE INDEX IF NOT EXISTS ux_question_tags_pair
    ON question_tags (question_id, tag_id);

COMMIT;

-- ============================================================
-- 验证
--   \d tags
--   \d question_tags
-- ============================================================
