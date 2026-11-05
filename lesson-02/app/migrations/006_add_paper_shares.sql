-- ============================================================
-- 006_add_paper_shares.sql · 试卷分享链接（lesson-24 · 原型 ⑧）
--
-- 干什么：
--   老师组完卷生成一个带过期时间的分享链接，发到微信群 / 学生家长。
--   对方点开在浏览器里看卷子、下 PDF / JPG，**不需要账号**。
--
-- 为什么需要一张新表：
--   分享是「一次授权、限时、可吊销」的三元组 —— 属于哪张卷、什么时候失效、
--   还能不能用，离开表就存不下。挂在 papers 上加两列解决不了「一张卷多个链接」。
--
-- 依赖：001（users）、002（sessions）已执行；papers 表由 lesson-09 建
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/006_add_paper_shares.sql
-- ============================================================

BEGIN;

-- ---------- 1. 分享链接表 ----------
CREATE TABLE IF NOT EXISTS paper_shares (
    id              SERIAL PRIMARY KEY,
    -- 谁的卷 —— 分享必须由卷的主人发起
    -- ⚠️ ON DELETE CASCADE：主人删了卷 / 账号被删 → 分享链接跟着消失。
    --    否则链接还在（却打不开），还占着一条指向空卷的记录；
    --    而且别的测试/脚本按外键顺序清库时会卡在这张表上。
    user_id         INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- 分享的是哪张卷
    paper_id        INTEGER      NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    -- 链接里的凭证（URL-safe 随机数，32 字节）
    -- ⚠️ 明文存：老师要能反复复制同一个链接（这周班级群、下周补课群），
    --    存哈希就永远拿不回原文了。泄露面受限于「单张卷只读 + 限时 + 可吊销」。
    token           VARCHAR(64)  NOT NULL,
    -- 必带过期时间 ——「带过期时间」是这节课的核心，不允许永久链接
    expires_at      TIMESTAMPTZ  NOT NULL,
    -- 吊销时间（非空 = 已作废）
    revoked_at      TIMESTAMPTZ,
    -- 审计字段：备案要求记录访问日志，分享链接是唯一对外暴露数据的口子
    view_count      INTEGER      NOT NULL DEFAULT 0,
    last_viewed_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_paper_shares_user_id ON paper_shares (user_id);
CREATE INDEX IF NOT EXISTS ix_paper_shares_paper_id ON paper_shares (paper_id);
CREATE INDEX IF NOT EXISTS ix_paper_shares_expires_at ON paper_shares (expires_at);

-- token 唯一（索引已带 unique，这里用唯一索引保证「拿链接查」不歧义）
CREATE UNIQUE INDEX IF NOT EXISTS ux_paper_shares_token ON paper_shares (token);

COMMIT;

-- ============================================================
-- 验证
--   \d paper_shares
--   SELECT count(*) FROM paper_shares;
-- ============================================================
