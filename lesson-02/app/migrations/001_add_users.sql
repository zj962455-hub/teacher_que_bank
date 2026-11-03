-- ============================================================
-- 001_add_users.sql · 引入用户体系（lesson-11 起）
--
-- 为什么要手写 SQL 而不是用 create_all：
--   SQLModel 的 create_all() 只创建**缺失的表**，
--   不会给**已存在的表加列** —— 线上库已经有 questions/papers，
--   直接改 models.py 后 create_all 跑一遍，user_id 列根本不会出现。
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/001_add_users.sql
--
-- 回滚：
--   见文件末尾注释（先备份再改，删列前务必确认没有数据依赖）
-- ============================================================

BEGIN;

-- ---------- 1. 建 users 表 ----------
-- id 用 SERIAL（PostgreSQL 自增序列，从 1 开始）
CREATE TABLE IF NOT EXISTS users (
    id                    SERIAL PRIMARY KEY,
    username              VARCHAR(50)  NOT NULL UNIQUE,
    display_name          VARCHAR(50)  NOT NULL DEFAULT '',
    password_hash         VARCHAR(255) NOT NULL,
    must_change_password  BOOLEAN      NOT NULL DEFAULT TRUE,
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at         TIMESTAMPTZ
);

-- username 唯一索引（UNIQUE 约束自带，这里额外建普通索引只为查询更快）
CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

-- ---------- 2. 给已有表加 user_id 列 ----------
-- 先可空 → 填数据 → 再改 NOT NULL。
-- 直接 ADD COLUMN ... NOT NULL 会因为存量行没有默认值而失败。
ALTER TABLE questions ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users (id);
ALTER TABLE papers    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users (id);

-- ---------- 3. 存量数据归属 ----------
-- 老师说要挂 test1 名下 —— 用 username 查 id，避免写死数字。
DO $$
DECLARE
    v_owner_id INTEGER;
BEGIN
    SELECT id INTO v_owner_id FROM users WHERE username = 'test1';

    IF v_owner_id IS NULL THEN
        RAISE EXCEPTION '用户 test1 不存在，先建号再跑迁移';
    END IF;

    -- 存量题目/试卷归到 test1
    UPDATE questions SET user_id = v_owner_id WHERE user_id IS NULL;
    UPDATE papers    SET user_id = v_owner_id WHERE user_id IS NULL;

    RAISE NOTICE '存量数据已归属 test1 (id=%)', v_owner_id;
END $$;

-- ---------- 4. 改成 NOT NULL ----------
-- 此刻已无 NULL 行，改成 NOT NULL 不会失败
ALTER TABLE questions ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE papers    ALTER COLUMN user_id SET NOT NULL;

-- ---------- 5. 索引 ----------
-- 隔离查询几乎总是「WHERE user_id = ?」，必须有索引
CREATE INDEX IF NOT EXISTS ix_questions_user_id ON questions (user_id);
CREATE INDEX IF NOT EXISTS ix_papers_user_id ON papers (user_id);

-- ---------- 6. 序列对齐 ----------
-- users 表刚建，序列从 1 开始；这里显式 setval 只是保证语义清晰
SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1), true);

COMMIT;

-- ============================================================
-- 验证（跑完应该看到 user_id 全非空）
--   SELECT count(*) FROM questions WHERE user_id IS NULL;  -- 应为 0
--   \d users
-- ============================================================
--
-- 回滚（谨慎：会丢失归属关系）
--   ALTER TABLE questions DROP COLUMN IF EXISTS user_id;
--   ALTER TABLE papers    DROP COLUMN IF EXISTS user_id;
--   DROP TABLE IF EXISTS users;
