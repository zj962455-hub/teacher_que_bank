"""反馈路由 — 课 34（老师反馈收集）

三个接口
--------
| 方法 | 路径 | 作用 | 谁能用 |
|---|---|---|---|
| POST | /api/feedback | 提交反馈 | 登录用户 |
| GET  | /api/feedback | 看反馈 | 登录用户（普通用户只看自己的，管理员看全部）|
| PATCH | /api/feedback/{id} | 改处理状态 | **仅管理员**|

再加两个**仅管理员**的统计接口（老大要拿「反馈结果」）：
| GET | /api/feedback/summary | 汇总统计（总数/分类/状态/提交人） | **仅管理员** |
| GET | /api/feedback/export | 导出（markdown / csv） | **仅管理员** |

为什么普通用户只能看自己的
--------------------------
反馈是**一对一的吐槽**——「这个按钮点不动」「导出 PDF 排版乱了」。
互相可见没有价值，只会让老师看到别人的吐槽后不想提了
（反正大家都看到了，就没必要专门提给我看）。

而且这跟仓库里其它数据一个口径：题目、试卷、反馈都是「我的就是我的」，
只有管理员为了「处理反馈」才需要看到全部 + 提交人。

共享账号下「谁提的」
-------------------
灰度阶段几个老师**共用一个账号** → ``user_id`` 全是同一个，
光看 user_id 分不出哪条反馈是谁提的。所以提交时额外收一个
``reporter``（老师自报身份，如「张老师·市三中」）+ ``contact``（选填）。

``reporter`` 为空时后端用当前用户的 ``display_name`` 兜底 ——
老师不改也不至于交上来一条「不知道谁提的」。

处理状态
--------
``new``（新）→ ``read``（已读）→ ``resolved``（已处理）。
不只是收集，是**收集到并且处理了**才算数 —— 所以状态跟内容存在同一张表。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Feedback, User
from app.services.auth import get_current_user, require_admin
from app.services.errors import (
    CODE_NOT_FOUND,
    CODE_VALIDATION,
    ApiHTTPException,
)

router = APIRouter(
    prefix="/feedback",
    tags=["反馈"],
)

# === 常量 ===

# 类别（固定三样，多了老师选不明白）
CATEGORIES = ("bug", "feature", "other")

# 处理状态
STATUSES = ("new", "read", "resolved")

# 正文长度（5–2000 字）
MIN_CONTENT = 5
MAX_CONTENT = 2000

# 类别中文名（前端展示用，后端也存一份 —— 导出/脚本用得到）
CATEGORY_LABELS = {
    "bug": "功能异常",
    "feature": "功能建议",
    "other": "其它",
}

STATUS_LABELS = {
    "new": "待处理",
    "read": "已读",
    "resolved": "已处理",
}


# === 请求体 / 响应体 ===

class FeedbackCreate(BaseModel):
    """提交反馈

    ⚠️ 长度上限在这里挡（2000），下限在路由里手写校验（5）——
       下限要返一句中文（「至少写 5 个字吧」），不是 422 校验数组。

    ``reporter`` / ``contact`` 是共享账号下的「谁提的」：
    reporter 为空时后端用 display_name 兜底，contact 可以一直空着。
    """

    category: str = Field(default="other", max_length=20)
    content: str = Field(max_length=MAX_CONTENT)
    page_url: str = Field(default="", max_length=500)
    reporter: str = Field(default="", max_length=50)
    contact: str = Field(default="", max_length=100)


class FeedbackStatusUpdate(BaseModel):
    """改处理状态（管理员）"""

    status: str = Field(max_length=20)


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    # 管理员视角才有值（普通用户看自己的，不需要知道自己是谁）
    username: str | None = None
    display_name: str | None = None
    category: str
    category_label: str
    content: str
    page_url: str
    status: str
    status_label: str
    created_at: str
    # 共享账号下的「谁提的」（reporter 为空则后端已用 display_name 兜底）
    reporter: str = ""
    contact: str = ""


class FeedbackListOut(BaseModel):
    items: list[FeedbackOut]
    total: int


# === 提交 ===

@router.post("", response_model=FeedbackOut)
def create_feedback(
    payload: FeedbackCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """提交一条反馈（需登录）"""
    category = (payload.category or "other").strip().lower()
    if category not in CATEGORIES:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="反馈类别不合法",
            code=CODE_VALIDATION,
        )

    content = (payload.content or "").strip()
    if len(content) < MIN_CONTENT:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"反馈内容太短了，至少写 {MIN_CONTENT} 个字",
            code=CODE_VALIDATION,
        )
    if len(content) > MAX_CONTENT:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"反馈内容太长了，最多 {MAX_CONTENT} 字",
            code=CODE_VALIDATION,
        )

    record = Feedback(
        user_id=user.id or 0,
        category=category,
        content=content,
        page_url=(payload.page_url or "").strip()[:500],
        # 共享账号下靠 reporter 分辨是谁提的；
        # 老师没填就用账号显示名兜底（共享账号的显示名就是账号名，也比空强）
        reporter=(payload.reporter or "").strip()[:50]
        or (user.display_name or "").strip()[:50]
        or (user.username or "").strip()[:50],
        contact=(payload.contact or "").strip()[:100],
        status="new",
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    return _feedback_out(record, user)


# === 列表 ===

@router.get("", response_model=FeedbackListOut)
def list_feedbacks(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """看反馈（需登录）

    - 普通用户：只看自己提的
    - 管理员：看全部，带提交人用户名（不然不知道该找谁）
    """
    if user.is_admin:
        records = session.exec(
            select(Feedback).order_by(Feedback.created_at.desc()).limit(500)
        ).all()
    else:
        records = session.exec(
            select(Feedback)
            .where(Feedback.user_id == (user.id or 0))
            .order_by(Feedback.created_at.desc())
            .limit(500)
        ).all()

    # 一次把提交人捞出来（管理员视角要显示用户名；普通用户看自己的用不上）
    users = _users_by_id(session, list({r.user_id for r in records}))

    items = [_feedback_out(r, users.get(r.user_id)) for r in records]
    return {"items": items, "total": len(items)}


# === 改状态（仅管理员）===

@router.patch("/{feedback_id}", response_model=FeedbackOut)
def update_feedback_status(
    feedback_id: int,
    payload: FeedbackStatusUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """改处理状态（仅管理员）

    普通用户调这个接口 → 403 auth.forbidden（接口层面挡，不靠前端藏按钮）。
    """
    new_status = (payload.status or "").strip().lower()
    if new_status not in STATUSES:
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="状态不合法（只能是 new / read / resolved）",
            code=CODE_VALIDATION,
        )

    record = session.get(Feedback, feedback_id)
    if record is None:
        raise ApiHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="反馈不存在",
            code=CODE_NOT_FOUND,
        )

    record.status = new_status
    session.add(record)
    session.commit()
    session.refresh(record)

    author = session.get(User, record.user_id)
    return _feedback_out(record, author)


# === 汇总统计（仅管理员）===

@router.get("/summary")
def feedback_summary(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """反馈汇总统计（**仅管理员**）

    老大要的是「老师用了一段时间后的反馈结果」——
    不只是一堆列表，而是：一共多少条、哪些还没处理、哪几位老师提的。

    ``contributors`` 是共享账号下的关键：
    几个老师共用一个 ``test2`` → ``user_id`` 全一样，
    只能靠 ``reporter`` 分辨是谁提的（没自报则回落账号名）。
    """
    records = session.exec(
        select(Feedback).order_by(Feedback.created_at.asc())
    ).all()
    users = _users_by_id(session, list({r.user_id for r in records}))

    by_category = {c: 0 for c in CATEGORIES}
    by_status = {s: 0 for s in STATUSES}
    contributors: dict[str, dict] = {}

    for r in records:
        by_category[r.category] = by_category.get(r.category, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1

        author = users.get(r.user_id)
        username = author.username if author else ""
        display_name = (author.display_name or "") if author else ""
        reporter = (r.reporter or "").strip()
        # 聚合键：reporter 优先（区分老师），没自报则回落账号名
        key = reporter or username or f"user-{r.user_id}"
        entry = contributors.get(key)
        if entry is None:
            contributors[key] = {
                "username": username,
                "display_name": display_name,
                "reporter": reporter,
                "count": 1,
            }
        else:
            entry["count"] += 1

    first_at = ""
    last_at = ""
    if records:
        if records[0].created_at:
            first_at = records[0].created_at.isoformat()
        if records[-1].created_at:
            last_at = records[-1].created_at.isoformat()

    return {
        "total": len(records),
        "by_category": by_category,
        "by_status": by_status,
        "new_count": by_status.get("new", 0),
        "resolved_count": by_status.get("resolved", 0),
        "first_at": first_at,
        "last_at": last_at,
        # 多的排前面 —— 老大先看提得最多的那位老师
        "contributors": sorted(
            contributors.values(),
            key=lambda c: (-c["count"], c["reporter"] or c["username"]),
        ),
    }


# === 导出（仅管理员）===

@router.get("/export")
def export_feedbacks(
    fmt: str = Query(default="markdown", alias="format", max_length=20),
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """导出反馈（**仅管理员**）

    - ``markdown`` —— 按类别分组，每条含日期 / 提交人 / 联系方式 / 状态 /
      内容 / 来源页面。老大要能**直接转发到微信群或存档**。
    - ``csv`` —— 标准 CSV，**带 BOM**（Excel 打开中文不乱码）。
    """
    kind = (fmt or "").strip().lower()
    if kind not in ("markdown", "csv"):
        raise ApiHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="导出格式只能是 markdown 或 csv",
            code=CODE_VALIDATION,
        )

    records = session.exec(
        select(Feedback).order_by(Feedback.created_at.asc())
    ).all()
    users = _users_by_id(session, list({r.user_id for r in records}))

    if kind == "csv":
        return Response(
            content=_to_csv(records, users),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="feedbacks.csv"',
            },
        )

    return Response(
        content=_to_markdown(records, users),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="feedbacks.md"',
        },
    )


# === 导出辅助 ===

# CSV 注入防护：Excel 会把以 = + - @ 开头的单元格当**公式**执行
# （=cmd|... 这类公式注入能骗到本地程序）。开头是制表符/回车的同理。
_CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """CSV 单元格转义 —— 防公式注入

    命中危险开头就在前面加一个单引号 —— Excel 当普通文本看。
    """
    if not value:
        return ""
    if value[0] in _CSV_DANGEROUS:
        return "'" + value
    # 前导空白 + 危险字符：某些 Excel 版本会先 trim 再当公式看
    stripped = value.lstrip(" \t\r\n")
    if stripped[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _reporter_of(record: Feedback, author: Optional[User]) -> str:
    """一条反馈的「提交人」显示名 —— reporter 优先，回落账号显示名/用户名"""
    reporter = (record.reporter or "").strip()
    if reporter:
        return reporter
    if author:
        return author.display_name or author.username
    return ""


def _to_csv(records: list[Feedback], users: dict[int, User]) -> str:
    """反馈 → CSV 文本（带 BOM）"""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        ["日期", "提交人", "账号", "联系方式", "状态", "类别", "内容", "来源页面"]
    )
    for r in records:
        author = users.get(r.user_id)
        writer.writerow([
            _csv_safe(r.created_at.isoformat() if r.created_at else ""),
            _csv_safe(_reporter_of(r, author)),
            _csv_safe(author.username if author else ""),
            _csv_safe(r.contact or ""),
            _csv_safe(STATUS_LABELS.get(r.status, r.status)),
            _csv_safe(CATEGORY_LABELS.get(r.category, r.category)),
            _csv_safe(r.content or ""),
            _csv_safe(r.page_url or ""),
        ])
    # ⚠️ BOM：Excel 打开不带 BOM 的 UTF-8 CSV 会按 GBK 猜 → 中文乱码
    return "\ufeff" + buf.getvalue()


def _fmt_dt(dt) -> str:
    """时间 → 「2026-11-06 21:46」（本地时区）"""
    if dt is None:
        return "（未知时间）"
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return str(dt)


def _to_markdown(records: list[Feedback], users: dict[int, User]) -> str:
    """反馈 → Markdown 文本（按类别分组）"""
    lines: list[str] = []
    total = len(records)
    by_status: dict[str, int] = {s: 0 for s in STATUSES}
    for r in records:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    lines.append("# 老师反馈汇总")
    lines.append("")
    lines.append(f"- 导出时间：{_fmt_dt(datetime.now(timezone.utc))}")
    lines.append(f"- 反馈总数：{total}")
    lines.append(
        "- 处理情况：待处理 {new} · 已读 {read} · 已处理 {resolved}".format(
            new=by_status.get("new", 0),
            read=by_status.get("read", 0),
            resolved=by_status.get("resolved", 0),
        )
    )
    lines.append("")

    if not records:
        lines.append("（暂无反馈）")
        lines.append("")
        return "\n".join(lines)

    # 按类别分组
    grouped: dict[str, list[Feedback]] = {c: [] for c in CATEGORIES}
    for r in records:
        grouped.setdefault(r.category, []).append(r)

    for cat in CATEGORIES:
        items = grouped.get(cat) or []
        if not items:
            continue
        lines.append(f"## {CATEGORY_LABELS.get(cat, cat)}（{len(items)} 条）")
        lines.append("")
        for idx, r in enumerate(items, 1):
            author = users.get(r.user_id)
            reporter = _reporter_of(r, author)
            lines.append(f"### {idx}. {_fmt_dt(r.created_at)} · {reporter or '（未署名）'}")
            lines.append(f"- 联系方式：{r.contact or '（未留）'}")
            lines.append(f"- 状态：{STATUS_LABELS.get(r.status, r.status)}")
            lines.append(f"- 来源页面：{r.page_url or '（未记录）'}")
            lines.append("- 内容：")
            lines.append("")
            content = (r.content or "").replace("\r\n", "\n").replace("\r", "\n")
            for line in content.split("\n"):
                lines.append(f"> {line}" if line else ">")
            lines.append("")

    return "\n".join(lines)


# === 辅助 ===

def _users_by_id(session: Session, user_ids: set[int]) -> dict[int, User]:
    """批量取用户（避免一条条查）"""
    if not user_ids:
        return {}
    result = {}
    for u in session.exec(select(User).where(User.id.in_(user_ids))).all():
        result[u.id or 0] = u
    return result


def _feedback_out(record: Feedback, author: Optional[User] = None) -> FeedbackOut:
    """反馈 → 返回体"""
    return FeedbackOut(
        id=record.id or 0,
        user_id=record.user_id,
        username=author.username if author else None,
        display_name=(author.display_name or None) if author else None,
        category=record.category,
        category_label=CATEGORY_LABELS.get(record.category, "其它"),
        content=record.content,
        page_url=record.page_url,
        status=record.status,
        status_label=STATUS_LABELS.get(record.status, record.status),
        created_at=record.created_at.isoformat() if record.created_at else "",
        reporter=record.reporter or "",
        contact=record.contact or "",
    )
