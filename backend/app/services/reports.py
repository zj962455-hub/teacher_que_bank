"""
举报受理服务 —— 站内举报的登记、限流与处置

为什么要有这一层
----------------
《网络安全责任告知书》第五条（六）要求：「建立标识、举报制度、公开举报、举报方式等
信息举报渠道的畅通、及时发现并处理相关有害信息的情况」。

原来平台只有页脚两个外链（12377、公安网络违法犯罪举报网站）—— 那是把用户导去别处，
平台自己**不受理、不记录、不知道有没有处理**。审核问「举报渠道是否畅通、有无及时
发现并处理」时，只能答「有外链」，答不出闭环。

这一层把闭环补上：

    公开提交（可匿名）→ 生成受理编号 → 管理员受理与处置 → 回填处置结论
    → 举报人凭受理编号查询进展

三条硬规矩
----------
1. **可匿名**：公开分享页的访客没有账号，强制登录就等于把渠道堵死 —— 而官方要的
   恰恰是「公开举报、渠道畅通」。
2. **有限流**：可匿名就可能被刷。同一 IP 一小时内超过上限直接拒，避免举报表被灌水。
3. **不抄正文**：只记「举报了什么东西、属于哪类问题」，不把被举报内容抄进表里。
"""

import secrets
import string
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models.report import Report

# === 举报理由 ===
# 与官方「违法有害信息」口径对齐，前端下拉与后台统计共用这一份
REASONS: dict[str, str] = {
    "illegal": "违法违规内容",
    "fraud": "诈骗或黑产引流",
    "porn": "色情低俗",
    "violence": "暴力恐怖",
    "copyright": "侵犯知识产权",
    "other": "其他",
}

# === 处置状态 ===
STATUSES = ("pending", "processing", "resolved", "rejected")

STATUS_LABELS = {
    "pending": "待受理",
    "processing": "核实中",
    "resolved": "已处置",
    "rejected": "不予受理",
}

# === 可被举报的对象类型 ===
TARGET_TYPES = ("question", "paper", "share", "upload", "user", "other")

# === 处置动作 ===
DISPOSE_ACTIONS = ("none", "delete_question", "revoke_share", "disable_account")

# 同一 IP 一小时最多提交多少条举报（防刷）
MAX_REPORTS_PER_IP_PER_HOUR = 20

# 受理编号字母表（去掉容易看错的 0/O/1/I）
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_report_no() -> str:
    """生成受理编号 —— 形如 R7K2M9QX4TB

    这个编号同时是**举报人的查询凭证**：拿到编号就能查进展，
    所以必须足够随机（11 位 × 31 字符集），不能自增。
    """
    body = "".join(secrets.choice(_ALPHABET) for _ in range(11))
    return "R" + body


def clean_text(value: str, limit: int) -> str:
    """清洗用户填的文本：去掉控制字符与零宽字符，限长

    为什么要洗
    ----------
    举报内容是用户可写的，直接存进管理后台会带进两类麻烦：
    - **零宽字符**：同一个词可以插入零宽空格变成「违 法」来躲过关键词检查；
    - **控制字符**：换行/制表符塞进导出表格会撑坏列结构。

    所以入库前统一剥掉，只留可打印内容。
    """
    if not value:
        return ""
    out = []
    for ch in value:
        if unicodedata.category(ch) in ("Cc", "Cf"):
            continue
        out.append(ch)
    return "".join(out).strip()[:limit]


def is_rate_limited(session: Session, source_ip: str) -> bool:
    """同一 IP 一小时内提交次数超限 → True

    查的是举报表本身（不另建计数表）—— 少一张表少一份同步。
    """
    if not source_ip:
        return False
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    count = session.exec(
        select(Report)
        .where(Report.source_ip == source_ip)
        .where(Report.created_at >= since)
    ).all()
    return len(count) >= MAX_REPORTS_PER_IP_PER_HOUR


def submit_report(
    session: Session,
    *,
    target_type: str,
    target_id: Optional[int],
    target_desc: str,
    reason: str,
    detail: str,
    reporter_user_id: Optional[int],
    reporter_name: str,
    reporter_contact: str,
    source_ip: str,
) -> Report:
    """登记一条举报，返回带受理编号的记录"""
    report = Report(
        report_no=generate_report_no(),
        target_type=target_type if target_type in TARGET_TYPES else "other",
        target_id=target_id,
        target_desc=clean_text(target_desc, 300),
        reason=reason if reason in REASONS else "other",
        detail=clean_text(detail, 1000),
        reporter_user_id=reporter_user_id,
        reporter_name=clean_text(reporter_name, 50),
        reporter_contact=clean_text(reporter_contact, 100),
        source_ip=(source_ip or "")[:45],
        status="pending",
        dispose_action="none",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_reports(
    session: Session,
    *,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[Report]:
    """列出举报（管理员用），按时间倒序"""
    stmt = select(Report)
    if status:
        stmt = stmt.where(Report.status == status)
    stmt = stmt.order_by(Report.created_at.desc()).limit(limit)
    return list(session.exec(stmt).all())


def get_by_report_no(session: Session, report_no: str) -> Optional[Report]:
    """按受理编号取一条举报（举报人查询进展用）"""
    return session.exec(
        select(Report).where(Report.report_no == report_no)
    ).first()


def count_by_status(session: Session) -> dict[str, int]:
    """按状态统计（管理员概览用）"""
    rows = session.exec(select(Report)).all()
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    counts["total"] = len(rows)
    return counts


def apply_dispose(
    session: Session,
    report: Report,
    action: str,
) -> str:
    """执行处置动作，返回一句话说明

    支持三种（都是**内容处置**，不是删账号这种一刀切）：
    - delete_question  删除被举报的题目（连带清理其图片文件）
    - revoke_share     吊销被举报的分享链接（对外通道立刻失效）
    - disable_account  停用被举报的账号（会话全部失效）

    ⚠️ 动作只做一次 —— 已经在报告上记了动作的，不重复执行
    （重复删题会找不到对象、重复停用会误伤）。
    """
    if action == "none":
        return ""

    if action == "delete_question":
        from app.models.paper import PaperQuestion
        from app.models.question import Question

        if report.target_id is None:
            return "未指定题目，无法删除"
        question = session.get(Question, report.target_id)
        if question is None:
            return "题目已不存在"
        # 复用题目删除里的图片清理逻辑（带引用计数保护）
        from app.routers.questions import _cleanup_question_images

        removed = _cleanup_question_images(session, question)
        for pq in session.exec(
            select(PaperQuestion).where(PaperQuestion.question_id == question.id)
        ).all():
            session.delete(pq)
        session.delete(question)
        session.commit()
        extra = "，并清理 %d 个图片文件" % len(removed) if removed else ""
        return "已删除被举报题目%s" % extra

    if action == "revoke_share":
        from app.models.paper import PaperShare

        if report.target_id is None:
            return "未指定分享链接，无法吊销"
        share = session.get(PaperShare, report.target_id)
        if share is None:
            return "分享链接已不存在"
        if share.revoked_at is None:
            share.revoked_at = datetime.now(timezone.utc)
            session.commit()
        return "已吊销被举报的分享链接"

    if action == "disable_account":
        from app.models.account import User
        from app.services.auth import revoke_all_sessions

        if report.target_id is None:
            return "未指定账号，无法停用"
        user = session.get(User, report.target_id)
        if user is None:
            return "账号已不存在"
        if user.is_active:
            user.is_active = False
            session.commit()
        revoked = revoke_all_sessions(session, user.id)
        return "已停用被举报账号，并注销其 %d 个登录会话" % revoked

    return ""
