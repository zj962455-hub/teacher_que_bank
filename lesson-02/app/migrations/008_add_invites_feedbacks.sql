-- ============================================================
-- 008_add_invites_feedbacks.sql · 灰度试用入口 + 老师反馈（lesson-34）
--
-- 干什么：
--   1) invites   —— 邀请码表。老师拿到码自己注册（灰度试用的入口），
--                    管理员控制「谁能进、能进几个、到什么时候」。
--   2) feedbacks —— 反馈表。老师提意见（bug / 想要的功能 / 其它），
--                    管理员在后台改处理状态。
--   3) users.is_admin —— 管理员标记。邀请码管理和反馈处理都要它。
--   4) users.allow_password_change —— 共享试用账号禁改密（改密会踢掉全员会话）。
--   5) feedbacks.reporter / feedbacks.contact —— 反馈带「谁提的」（共享账号下区分老师）。
--
-- 为什么邀请码要一张表而不是 users 上加一列
-- ------------------------------------------
-- 邀请码是「一次性/限次的准入凭证」：码本身、用了几次、到什么时候、停没停。
-- 这些都是**码自己的属性**，不是人的属性 —— 挂到 users 上就没有地方放。
--
-- 依赖：001（users）已执行
--
-- 执行：
--   PGPASSWORD=*** psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
--     -v ON_ERROR_STOP=1 -f migrations/008_add_invites_feedbacks.sql
-- ============================================================

BEGIN;

-- ---------- 0. 管理员标记 ----------
-- ⚠️ ADD COLUMN IF NOT EXISTS：重复执行不报错（迁移脚本要能重跑）。
--    NOT NULL DEFAULT false：老账号自动是普通用户，不用回填。
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_users_is_admin ON users (is_admin);

-- ---------- 0.1 共享账号禁改密 ----------
-- ⚠️ 灰度阶段几个老师共用一个账号 test2：改密码会 revoke_all_sessions，
--    **一人改密 = 全员被踢下线**。所以共享账号把这一列置 false，
--    改密接口直接 403（后端拦，前端只是提示）。
--    NOT NULL DEFAULT true：老账号默认允许改密，不用回填。
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS allow_password_change BOOLEAN NOT NULL DEFAULT true;

-- ---------- 1. 邀请码表 ----------
CREATE TABLE IF NOT EXISTS invites (
    id                  SERIAL PRIMARY KEY,
    -- 邀请码本身（明文存：管理员要能反复复制分发，见 models.py 的说明）
    code                VARCHAR(32)  NOT NULL,
    -- 备注：给谁发的、哪个批次
    label               VARCHAR(50)  NOT NULL DEFAULT '',
    -- 名额：最多能用几次 / 已经用了几次
    max_uses            INTEGER      NOT NULL DEFAULT 1,
    used_count          INTEGER      NOT NULL DEFAULT 0,
    -- 过期时间（NULL = 永不过期）
    expires_at          TIMESTAMPTZ,
    -- 停用开关（发错了 / 老师流失了 → 一键停）
    is_active           BOOLEAN      NOT NULL DEFAULT true,
    -- 谁发的（可空：批量脚本生成的码没有具体的人）
    -- ⚠️ ON DELETE CASCADE：跟本仓库其它外键一致 —— 账号被删，发出的码一起清。
    created_by_user_id  INTEGER      REFERENCES users (id) ON DELETE CASCADE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 码唯一（拿码查人靠它）
CREATE UNIQUE INDEX IF NOT EXISTS ux_invites_code ON invites (code);
CREATE INDEX IF NOT EXISTS ix_invites_created_by_user_id ON invites (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_invites_expires_at ON invites (expires_at);
CREATE INDEX IF NOT EXISTS ix_invites_is_active ON invites (is_active);
-- 后台列表按创建时间倒序翻页
CREATE INDEX IF NOT EXISTS ix_invites_created_at ON invites (created_at DESC);

-- ---------- 2. 反馈表 ----------
CREATE TABLE IF NOT EXISTS feedbacks (
    id          SERIAL PRIMARY KEY,
    -- 谁提的
    -- ⚠️ ON DELETE CASCADE：账号被删 → 反馈一起删，不留孤儿记录。
    user_id     INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- 类别：bug / feature / other
    category    VARCHAR(20)  NOT NULL DEFAULT 'other',
    -- 正文
    content     TEXT         NOT NULL DEFAULT '',
    -- 提交人自报身份（「张老师·市三中」）—— 共享账号下靠它区分老师
    reporter    VARCHAR(50)  NOT NULL DEFAULT '',
    -- 联系方式（选填：微信 / 手机）—— 管理员跟进时用
    contact     VARCHAR(100) NOT NULL DEFAULT '',
    -- 提反馈时所在的页面（管理员复现问题用）
    page_url    VARCHAR(500) NOT NULL DEFAULT '',
    -- 处理状态：new / read / resolved
    status      VARCHAR(20)  NOT NULL DEFAULT 'new',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ⚠️ 重复执行不报错（表可能已存在 —— 补齐后加的两列）
ALTER TABLE feedbacks
    ADD COLUMN IF NOT EXISTS reporter VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE feedbacks
    ADD COLUMN IF NOT EXISTS contact VARCHAR(100) NOT NULL DEFAULT '';

-- 「我的反馈」列表：按 user_id 过滤 + 按时间倒序（组合索引，一步到位）
CREATE INDEX IF NOT EXISTS ix_feedbacks_user_created
    ON feedbacks (user_id, created_at DESC);
-- 管理员按状态筛选
CREATE INDEX IF NOT EXISTS ix_feedbacks_status ON feedbacks (status);

-- ---------- 权限 ----------
-- ⚠️ 迁移是 postgres 执行的,表默认归 postgres —— 应用账号(teacherbank)
--    读不了就 500(permission denied for table invites)。
--    所以建完表必须把权限给应用账号。
--    这几行可以重复执行(GRANT 幂等)。
GRANT ALL PRIVILEGES ON TABLE invites, feedbacks TO teacherbank;
GRANT ALL PRIVILEGES ON SEQUENCE invites_id_seq, feedbacks_id_seq TO teacherbank;

COMMIT;

-- ============================================================
-- 验证
--   \d invites
--   \d feedbacks
--   \d users
--   SELECT code, label, max_uses, used_count, is_active FROM invites ORDER BY id DESC;
--   SELECT username, is_admin, allow_password_change FROM users ORDER BY id DESC;
-- ============================================================
