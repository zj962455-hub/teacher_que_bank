-- ============================================================
-- 004_add_categories.sql · 章节分类树（lesson-11 · 原型 ⑥）
--
-- 为什么要有这张表：
--   之前的「章节树」是按 subject/grade/difficulty 三个字段拼出来的，
--   看着像树但改不了、拖不动、也没真正的归属关系。
--
-- 依赖：001（users）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/004_add_categories.sql
-- ============================================================

BEGIN;

-- ---------- 1. 建 categories 表 ----------
CREATE TABLE IF NOT EXISTS categories (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER      NOT NULL REFERENCES users (id),
    name       VARCHAR(50)  NOT NULL,
    parent_id  INTEGER      REFERENCES categories (id),
    sort_order INTEGER      NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories (user_id);
CREATE INDEX IF NOT EXISTS ix_categories_parent_id ON categories (parent_id);

-- ---------- 2. 题目挂到分类上 ----------
ALTER TABLE questions ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories (id);
CREATE INDEX IF NOT EXISTS ix_questions_category_id ON questions (category_id);

COMMIT;

-- ============================================================
-- 验证
--   \d categories
-- ============================================================
