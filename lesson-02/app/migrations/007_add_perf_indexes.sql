-- ============================================================
-- 007_add_perf_indexes.sql · 性能索引（lesson-33）
--
-- 干什么：
--   给「按用户 + 排序/筛选」的热点查询补上**组合索引**，
--   以及给关键词搜索加 **pg_trgm 全文模糊索引**。
--
-- 为什么现在才加
-- ------------
-- 建了 5 张表，每张只有单列索引（user_id / category_id / …）。
-- 但真实查询几乎都是「**按 user_id 过滤 + 按某个字段排序**」——
-- 单列索引只能过滤，排序还得再排一次（EXPLAIN 里能看到 Sort 节点）。
-- 老师题库到几千道题时，这就是「翻页越来越慢」的来源。
--
-- 依赖：001（users）、002（sessions）、004（categories）、005（tags）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/007_add_perf_indexes.sql
-- ============================================================

BEGIN;

-- ---------- 0. 关键词搜索要模糊匹配，pg_trgm 是唯一能吃住 ILIKE '%x%' 的索引 ----------
-- ⚠️ 没有它，搜索是全表扫描（Seq Scan + Filter）。
--    扩展装在 public schema（所有用户可用），不需要超级用户之外的额外授权。
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------- 1. 题目列表：按用户 + 排序 ----------
-- 列表默认按 created_at desc 排，筛选用 user_id。
-- 组合索引让「过滤 + 排序」一步到位（Index Scan 直接出有序结果，省掉 Sort 节点）。
CREATE INDEX IF NOT EXISTS ix_questions_user_created
    ON questions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_questions_user_updated
    ON questions (user_id, updated_at DESC);

-- 分类筛选 + 用户过滤（题目列表可按 category_id 筛）
CREATE INDEX IF NOT EXISTS ix_questions_user_category
    ON questions (user_id, category_id);

-- 关键词模糊搜索（GIN + trigram）
CREATE INDEX IF NOT EXISTS ix_questions_content_plain_trgm
    ON questions USING GIN (content_plain gin_trgm_ops);

-- ---------- 2. 试卷列表：按用户 + 创建时间倒序 ----------
CREATE INDEX IF NOT EXISTS ix_papers_user_created
    ON papers (user_id, created_at DESC);

-- ---------- 3. 试卷里的题：按 paper_id 取 + 按 order_index 排 ----------
-- 导出 PDF / 试卷详情都要「这张卷的题按顺序排」，
-- 组合索引让它不用再 Sort 一次。
CREATE INDEX IF NOT EXISTS ix_paper_questions_paper_order
    ON paper_questions (paper_id, order_index);

-- ---------- 4. 标签反查：题目 → 标签 / 标签 → 题目 ----------
-- 唯一索引 ux_question_tags_pair 是 (question_id, tag_id)，
-- 按 tag_id 查题目时用不上 → 补一个反向的。
CREATE INDEX IF NOT EXISTS ix_question_tags_tag_question
    ON question_tags (tag_id, question_id);

-- ---------- 5. 分类树：按用户 + 父节点 + 排序 ----------
CREATE INDEX IF NOT EXISTS ix_categories_user_parent_sort
    ON categories (user_id, parent_id, sort_order, id);

-- ---------- 6. 会话列表：按用户 + 最近使用 ----------
CREATE INDEX IF NOT EXISTS ix_sessions_user_last_used
    ON sessions (user_id, last_used_at DESC);

COMMIT;

-- ============================================================
-- 验证
--   \d questions
--   \di ix_questions_user_created
--   EXPLAIN ANALYZE SELECT id, content_plain FROM questions
--     WHERE user_id = 1 ORDER BY created_at DESC LIMIT 50;
--   EXPLAIN ANALYZE SELECT id FROM questions
--     WHERE user_id = 1 AND content_plain ILIKE '%等差%';
-- ============================================================
