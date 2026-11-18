"""
合规服务 —— 面向监管与执法部门的数据调阅与协助（公安备案 · 安全评估）

提供两件能力
------------
1. **审计日志导出**（admin_only）：监管要调阅操作日志时，直接按条件导出 CSV，
   不用手工连库查。字段与安全评估要求的日志字段一一对应。
2. **调阅台账**：每次提供数据或协助都登记一条，谁要的、依据什么文书、
   给了什么、有没有回执 —— 机制留痕。

CSV 注入防护
------------
Excel 会把以 = + - @ 开头的单元格当**公式**执行（=cmd|... 这类公式注入
能骗到本地程序）。开头是制表符/回车的同理。导出前统一加前缀转义。
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models.audit import AuditLog

# 导出上限 —— 防止一次导出把内存打爆（审计表现在也不大，但留个闸）
EXPORT_MAX_ROWS = 50000


def _sanitize_cell(value: str) -> str:
    """CSV 注入防护：危险开头加单引号前缀"""
    if not value:
        return ""
    if value[0] in ("=", "+", "-", "@") or ord(value[0]) in (9, 13):
        return "'" + value
    return value


def query_audit_logs(
    session: Session,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    account: Optional[str] = None,
    ip: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = EXPORT_MAX_ROWS,
) -> list[AuditLog]:
    """按条件查审计日志（监管调阅用）"""
    stmt = select(AuditLog)
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.created_at <= until)
    if account:
        stmt = stmt.where(AuditLog.username == account)
    if ip:
        stmt = stmt.where(AuditLog.client_ip == ip)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.created_at.asc()).limit(limit)
    return list(session.exec(stmt).all())


def audit_logs_to_csv(rows: list[AuditLog]) -> str:
    """审计日志 → CSV（带 BOM，Excel 打开中文不乱码）"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "操作时间",
            "操作账号",
            "用户ID",
            "操作类型",
            "请求方法",
            "请求路径",
            "网络源地址",
            "网络源端口",
            "目标地址",
            "目标路径",
            "响应状态码",
            "耗时毫秒",
            "客户端特征",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                _sanitize_cell(
                    r.created_at.astimezone(timezone.utc)
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S")
                ),
                _sanitize_cell(r.username),
                _sanitize_cell(str(r.user_id or "")),
                _sanitize_cell(r.action),
                _sanitize_cell(r.method),
                _sanitize_cell(r.path),
                _sanitize_cell(r.client_ip),
                _sanitize_cell(r.client_port),
                _sanitize_cell(r.target_host),
                _sanitize_cell(r.target_path),
                _sanitize_cell(str(r.status_code)),
                _sanitize_cell(str(r.duration_ms)),
                _sanitize_cell(r.user_agent),
            ]
        )
    return "\ufeff" + buf.getvalue()
