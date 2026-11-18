"""
举报路由 —— 站内举报的公开受理、进展查询与管理员处置

接口一览
--------
| 方法 | 路径 | 作用 | 谁能用 |
|---|---|---|---|
| POST | /api/reports | 提交举报（**可匿名**） | 任何人（含未登录访客） |
| GET | /api/reports/track/{report_no} | 凭受理编号查处理进展 | 举报人（凭编号） |
| GET | /api/reports | 举报列表 | **仅管理员** |
| GET | /api/reports/summary | 状态统计 | **仅管理员** |
| PATCH | /api/reports/{id} | 受理 / 处置 / 回填结论 | **仅管理员** |

为什么提交接口不要求登录
------------------------
公开分享页（/share/:token）是站点**唯一**对外暴露内容的页面。访客看到一份有害
内容想举报，手里没有账号 —— 强制登录就等于把渠道堵死。而官方第（六）项要的恰恰是
「公开举报、渠道畅通」。所以：

- 提交**不要求登录**，登录了就顺手记下是谁（reporter_user_id），没登录就匿名；
- 处置**必须登录且是管理员**（接口层 require_admin，不是靠前端隐藏）。

举报人怎么知道处理结果
----------------------
提交时返回一个**受理编号**（形如 R7K2M9QX4TB）。凭编号可以查进展 —— 编号同时是
查询凭证，所以它必须足够随机（11 位 × 31 字符集），不能自增。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Report, User
from app.services.auth import get_current_user, get_optional_user, require_admin
from app.services.errors import (
    CODE_NOT_FOUND,
    CODE_VALIDATION,
    ApiHTTPException,
)
from app.services.reports import (
    DISPOSE_ACTIONS,
    MAX_REPORTS_PER_IP_PER_HOUR,
    REASONS,
    STATUS_LABELS,
    STATUSES,
    TARGET_TYPES,
    apply_dispose,
    count_by_status,
    get_by_report_no,
    is_rate_limited,
    list_reports,
    submit_report,
)

router = APIRouter(
    prefix="/reports",
    tags=["举报受理"],
)


class ReportCreate(BaseModel):
    """提交一条举报"""

    target_type: str = Field(default="other", max_length=20)
    target_id: Optional[int] = None
    target_desc: str = Field(default="", max_length=300)
    reason: str = Field(default="other", max_length=30)
    detail: str = Field(default="", max_length=1000)
    reporter_name: str = Field(default="", max_length=50)
    reporter_contact: str = Field(default="", max_length=100)


class ReportHandle(BaseModel):
    """管理员受理 / 处置一条举报"""

    status: str = Field(max_length=20)
    handle_note: str = Field(default="", max_length=1000)
    dispose_action: str = Field(default="none", max_length=30)


def _client_ip(request: Request) -> str:
    """取客户端 IP（限流与留痕用）

    经自家 nginx 时采信 X-Real-IP（nginx 用 proxy_set_header 覆盖客户端同名头，
    客户端伪造不了）；直连时用真实对端。
    """
    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        return x_real_ip[:45]
    peer = request.client.host if request.client else ""
    return peer[:45]


# ===================== 公开：提交举报 =====================


@router.post("")
def create_report(
    payload: ReportCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(get_optional_user),
):
    """提交举报（**不要求登录**，可匿名）

    返回受理编号 —— 举报人拿它查处理进展。
    """
    if payload.reason not in REASONS:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="举报类型不合法",
            code=CODE_VALIDATION,
        )
    if payload.target_type not in TARGET_TYPES:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="举报对象类型不合法",
            code=CODE_VALIDATION,
        )
    # 至少要说清楚「举报的是什么东西」或者「为什么」
    if not payload.detail.strip() and not payload.target_desc.strip():
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少填写举报对象或举报说明",
            code=CODE_VALIDATION,
        )

    source_ip = _client_ip(request)
    if is_rate_limited(session, source_ip):
        raise ApiHTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="举报提交过于频繁，请稍后再试",
            code="report.rate_limited",
        )

    report = submit_report(
        session,
        target_type=payload.target_type,
        target_id=payload.target_id,
        target_desc=payload.target_desc,
        reason=payload.reason,
        detail=payload.detail,
        reporter_user_id=(user.id if user else None),
        reporter_name=(user.display_name if user else payload.reporter_name),
        reporter_contact=payload.reporter_contact,
        source_ip=source_ip,
    )
    return {
        "report_no": report.report_no,
        "status": report.status,
        "status_label": STATUS_LABELS[report.status],
        "message": "举报已受理，请凭受理编号查询处理进展",
        "max_per_hour": MAX_REPORTS_PER_IP_PER_HOUR,
    }


# ===================== 公开：凭编号查进展 =====================


@router.get("/track/{report_no}")
def track_report(
    report_no: str,
    session: Session = Depends(get_session),
):
    """凭受理编号查询处理进展

    只回给举报人关心的东西：状态、处置结论、处置时间。
    **不回**举报人姓名、联系方式、来源 IP —— 那是内部信息。
    """
    report = get_by_report_no(session, report_no.strip().upper())
    if report is None:
        raise ApiHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该受理编号",
            code=CODE_NOT_FOUND,
        )
    return {
        "report_no": report.report_no,
        "status": report.status,
        "status_label": STATUS_LABELS.get(report.status, report.status),
        "reason_label": REASONS.get(report.reason, report.reason),
        "target_desc": report.target_desc,
        "handle_note": report.handle_note,
        "dispose_action": report.dispose_action,
        "created_at": report.created_at.isoformat(),
        "handled_at": report.handled_at.isoformat() if report.handled_at else None,
    }


# ===================== 管理员：列表与统计 =====================


@router.get("")
def admin_list_reports(
    status_filter: Optional[str] = Query(None, alias="status", max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """举报列表（**仅管理员**）"""
    if status_filter and status_filter not in STATUSES:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="状态值不合法",
            code=CODE_VALIDATION,
        )
    rows = list_reports(session, status=status_filter, limit=limit)
    return [
        {
            "id": r.id,
            "report_no": r.report_no,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "target_desc": r.target_desc,
            "reason": r.reason,
            "reason_label": REASONS.get(r.reason, r.reason),
            "detail": r.detail,
            "reporter_name": r.reporter_name,
            "reporter_contact": r.reporter_contact,
            "source_ip": r.source_ip,
            "status": r.status,
            "status_label": STATUS_LABELS.get(r.status, r.status),
            "handle_note": r.handle_note,
            "handled_by": r.handled_by,
            "handled_at": r.handled_at.isoformat() if r.handled_at else None,
            "dispose_action": r.dispose_action,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/summary")
def admin_report_summary(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """举报状态统计（**仅管理员**）"""
    counts = count_by_status(session)
    return {
        "counts": counts,
        "labels": STATUS_LABELS,
        "reasons": REASONS,
    }


# ===================== 管理员：受理与处置 =====================


@router.patch("/{report_id}")
def admin_handle_report(
    report_id: int,
    payload: ReportHandle,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """受理 / 处置一条举报（**仅管理员**）

    可同时指定处置动作 —— 处置动作**当场执行**（删题 / 吊销分享 / 停账号），
    执行结果并入处置结论回填给举报人。
    """
    report = session.get(Report, report_id)
    if report is None:
        raise ApiHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="举报记录不存在",
            code=CODE_NOT_FOUND,
        )
    if payload.status not in STATUSES:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="状态值不合法",
            code=CODE_VALIDATION,
        )
    if payload.dispose_action not in DISPOSE_ACTIONS:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="处置动作不合法",
            code=CODE_VALIDATION,
        )

    # 处置动作只做一次 —— 已经处置过的报告不再重复执行
    dispose_note = ""
    if payload.dispose_action != "none" and report.dispose_action == "none":
        dispose_note = apply_dispose(session, report, payload.dispose_action)
        report.dispose_action = payload.dispose_action

    report.status = payload.status
    report.handled_by = admin.username or ""
    report.handled_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    note = payload.handle_note.strip()
    if dispose_note:
        note = (note + "；" + dispose_note).strip("；") if note else dispose_note
    report.handle_note = note[:1000]

    session.add(report)
    session.commit()
    session.refresh(report)

    return {
        "id": report.id,
        "report_no": report.report_no,
        "status": report.status,
        "status_label": STATUS_LABELS.get(report.status, report.status),
        "handle_note": report.handle_note,
        "dispose_action": report.dispose_action,
        "handled_by": report.handled_by,
        "handled_at": report.handled_at.isoformat() if report.handled_at else None,
    }
