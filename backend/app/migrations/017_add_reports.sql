-- ============================================================
-- 017_add_reports.sql · 违法有害信息举报受理台账
--   （lesson-43 · 公安备案 · 安全评估第五条第（六）项）
--
-- 干什么：
--   新增 reports 表 —— 站内举报的受理、处置与反馈闭环。
--   官方要求「建立标识、举报制度、公开举报、举报方式等信息举报渠道的
--   畅通、及时发现并处理相关有害信息的情况」，原来平台只有页脚两个
--   外链，平台自己不受理、不记录 → 这张表把它补齐。
--
-- 只记「举报这件事」，不抄被举报内容正文。
--
-- 执行：
--   cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f 017_add_reports.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS reports (
    id                SERIAL PRIMARY KEY,
    report_no         VARCHAR(32)  NOT NULL,
    target_type       VARCHAR(20)  NOT NULL DEFAULT 'other',
    target_id         INTEGER,
    target_desc       VARCHAR(300) NOT NULL DEFAULT '',
    reason            VARCHAR(30)  NOT NULL DEFAULT 'other',
    detail            VARCHAR(1000) NOT NULL DEFAULT '',
    reporter_user_id  INTEGER,
    reporter_name     VARCHAR(50)  NOT NULL DEFAULT '',
    reporter_contact  VARCHAR(100) NOT NULL DEFAULT '',
    source_ip         VARCHAR(45)  NOT NULL DEFAULT '',
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending',
    handle_note       VARCHAR(1000) NOT NULL DEFAULT '',
    handled_by        VARCHAR(50)  NOT NULL DEFAULT '',
    handled_at        TIMESTAMPTZ,
    dispose_action    VARCHAR(30)  NOT NULL DEFAULT 'none',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_reports_report_no ON reports (report_no);
CREATE INDEX IF NOT EXISTS ix_reports_status ON reports (status);
CREATE INDEX IF NOT EXISTS ix_reports_created_at ON reports (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_reports_source_ip ON reports (source_ip);
CREATE INDEX IF NOT EXISTS ix_reports_target ON reports (target_type, target_id);

-- ---------- 权限 ----------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'teacherbank') THEN
        GRANT ALL PRIVILEGES ON TABLE reports TO teacherbank;
        GRANT ALL PRIVILEGES ON SEQUENCE reports_id_seq TO teacherbank;
    END IF;
END
$$;

COMMIT;

-- ============================================================
-- 验证：
--   SELECT report_no, target_type, reason, status, handled_by, handled_at
--     FROM reports ORDER BY id DESC LIMIT 10;
-- ============================================================
