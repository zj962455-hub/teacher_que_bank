-- ============================================================
-- 016_add_regulatory_requests.sql · 监管与执法调阅台账（lesson-42 · 公安备案 · 配合监管工作机制）
--
-- 干什么：
--   新增 regulatory_requests 表 —— 记录每一次向监管部门/执法部门
--   提供技术、数据支持或协助的情况（谁要的、依据什么文书、要什么、
--   给了什么、什么时候给的、有没有回执）。
--
-- 为什么需要：
--   安全评估要求「建立为监管部门和执法部门依法履职提供技术、数据支持和协助的工作机制」。
--   「机制」要留痕 —— 否则说不清什么时候配合了什么。
--
-- 只记调阅这件事本身，不记被调阅的业务内容。
--
-- 执行：
--   cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f 016_add_regulatory_requests.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS regulatory_requests (
    id             SERIAL PRIMARY KEY,
    authority      VARCHAR(100) NOT NULL DEFAULT '',
    requester      VARCHAR(100) NOT NULL DEFAULT '',
    basis          VARCHAR(300) NOT NULL DEFAULT '',
    scope          VARCHAR(500) NOT NULL DEFAULT '',
    data_provided  VARCHAR(500) NOT NULL DEFAULT '',
    channel        VARCHAR(50)  NOT NULL DEFAULT '平台导出',
    provided_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    provided_by    VARCHAR(50)  NOT NULL DEFAULT '',
    receipt_no     VARCHAR(100) NOT NULL DEFAULT '',
    notes          VARCHAR(500) NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_regulatory_requests_provided_at
    ON regulatory_requests (provided_at DESC);
CREATE INDEX IF NOT EXISTS ix_regulatory_requests_authority
    ON regulatory_requests (authority, provided_at DESC);

-- ---------- 权限 ----------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE regulatory_requests TO teacherbank;
        GRANT ALL PRIVILEGES ON SEQUENCE regulatory_requests_id_seq TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证：
--   SELECT provided_at, authority, scope, data_provided, receipt_no
--     FROM regulatory_requests ORDER BY id DESC LIMIT 10;
-- ============================================================
