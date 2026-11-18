"""
合规与监管配合路由 — lesson-42（公安备案 · 安全评估）

为什么要有这组接口
------------------
安全评估要求「建立为监管部门和执法部门依法履职提供技术、数据支持和协助的工作机制」。

机制要能落地，靠三件事：
1. **调得出来** —— 监管要日志，能按条件一键导出，不用手工连库；
2. **记得住** —— 每次调阅登记台账（谁要的、依据什么文书、给了什么、有没有回执）；
3. **留得下** —— 导出与登记动作本身也进操作审计日志。

⚠️ 全部接口**仅管理员**（require_admin 在接口层挡，前端隐藏入口不算）。
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import RegulatoryRequest, User
from app.services.auth import require_admin
from app.services.compliance import (
    EXPORT_MAX_ROWS,
    audit_logs_to_csv,
    query_audit_logs,
)
from app.services.errors import CODE_VALIDATION, ApiHTTPException

router = APIRouter(
    prefix="/compliance",
    tags=["合规与监管配合（仅管理员）"],
)


def _parse_dt(raw: Optional[str], field: str) -> Optional[datetime]:
    """把 ISO 字符串解析成带时区的 datetime"""
    if not raw:
        return None
    text = raw.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} 时间格式不对，用 ISO 格式，如 2026-11-01T00:00:00",
            code=CODE_VALIDATION,
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ===================== 审计日志导出 =====================


@router.get("/audit/export")
def export_audit_logs(
    since: Optional[str] = Query(None, alias="from", max_length=40),
    until: Optional[str] = Query(None, alias="to", max_length=40),
    account: Optional[str] = Query(None, max_length=50),
    ip: Optional[str] = Query(None, max_length=45),
    action: Optional[str] = Query(None, max_length=300),
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """导出操作审计日志（**仅管理员**）—— 监管/执法调阅用

    字段与安全评估要求的日志字段一一对应：操作时间、操作账号、操作类型、
    网络源地址与源端口、目标地址、客户端特征。

    返回 CSV（带 BOM，Excel 打开中文不乱码）。
    """
    start = _parse_dt(since, "from")
    end = _parse_dt(until, "to")
    if start and end and start > end:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from 不能晚于 to",
            code=CODE_VALIDATION,
        )

    rows = query_audit_logs(
        session,
        since=start,
        until=end,
        account=(account or None),
        ip=(ip or None),
        action=(action or None),
    )
    return Response(
        content=audit_logs_to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="audit_logs.csv"',
            "X-Export-Count": str(len(rows)),
            "X-Export-Limit": str(EXPORT_MAX_ROWS),
        },
    )


# ===================== 调阅台账 =====================


class RegulatoryRequestIn(BaseModel):
    """登记一次调阅 / 协助"""

    authority: str = Field(min_length=1, max_length=100)
    requester: str = Field(default="", max_length=100)
    basis: str = Field(default="", max_length=300)
    scope: str = Field(default="", max_length=500)
    data_provided: str = Field(default="", max_length=500)
    channel: str = Field(default="平台导出", max_length=50)
    provided_by: str = Field(default="", max_length=50)
    receipt_no: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=500)


@router.post("/requests")
def create_regulatory_request(
    payload: RegulatoryRequestIn,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """登记一次向监管/执法部门提供数据或协助的情况（**仅管理员**）"""
    record = RegulatoryRequest(
        authority=payload.authority.strip(),
        requester=payload.requester.strip(),
        basis=payload.basis.strip(),
        scope=payload.scope.strip(),
        data_provided=payload.data_provided.strip(),
        channel=payload.channel.strip() or "平台导出",
        provided_by=payload.provided_by.strip() or (admin.username or ""),
        receipt_no=payload.receipt_no.strip(),
        notes=payload.notes.strip(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return {
        "id": record.id,
        "authority": record.authority,
        "provided_at": record.provided_at.isoformat(),
        "provided_by": record.provided_by,
    }


@router.get("/requests")
def list_regulatory_requests(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """调阅台账列表（**仅管理员**，按时间倒序）"""
    rows = session.exec(
        select(RegulatoryRequest)
        .order_by(RegulatoryRequest.provided_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "authority": r.authority,
            "requester": r.requester,
            "basis": r.basis,
            "scope": r.scope,
            "data_provided": r.data_provided,
            "channel": r.channel,
            "provided_at": r.provided_at.isoformat(),
            "provided_by": r.provided_by,
            "receipt_no": r.receipt_no,
            "notes": r.notes,
        }
        for r in rows
    ]
