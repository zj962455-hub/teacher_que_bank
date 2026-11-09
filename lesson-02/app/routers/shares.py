"""分享链接路由 — lesson-24（原型 ⑧「生成分享链接」）

两条线
------
**管理线（要登录）**

| 方法 | 路径 | 作用 |
|---|---|---|
| POST   | /api/papers/{id}/shares          | 生成分享链接（卷的主人）|
| GET    | /api/papers/{id}/shares          | 这张卷的分享链接列表 |
| DELETE | /api/papers/{id}/shares/{share_id} | 吊销一条链接 |

**公开线（不用登录）**

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | /api/shares/{token}              | 看卷子（只读）|
| GET | /api/shares/{token}/export.pdf   | 下 PDF |
| GET | /api/shares/{token}/export.jpg   | 下 JPG（每页一张，ZIP）|

公开线为什么可以不要登录
----------------------
分享的意义就是「对方没有账号也能看」—— 老师把链接发到家长群，
家长点开就看到卷子。要求对方先注册账号，这条功能就没意义了。

代价是**这三条接口是唯一对外暴露题目内容的口子**，所以：
- token 是 32 字节随机数（256 位熵），猜不出来
- 必带过期时间，且可随时吊销
- 只返回这一张卷的内容，返回体里**没有任何用户信息**（不含 owner id / 用户名）
- 每次访问记 view_count / last_viewed_at（审计）
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Paper, PaperShare, User
from app.routers.papers import _paper_detail
from app.services.classifier import strip_figure_placeholder
from app.services.auth import get_current_user
from app.services.jpg_export import JpgExportError, build_jpg_zip
from app.services.pdf_export import PdfExportError, export_paper_pdf
from app.services.share import (
    ShareError,
    create_share,
    get_share,
    list_shares,
    resolve_share,
    revoke_share,
    share_state,
    touch_share,
)

# 管理线：挂在 /papers 下
manage_router = APIRouter(prefix="/papers", tags=["分享链接"])

# 公开线：挂在 /shares 下
public_router = APIRouter(prefix="/shares", tags=["分享链接（公开）"])


# === 请求体 ===
class ShareCreate(BaseModel):
    """生成分享链接

    expire_hours: 有效小时数，默认 7 天，最长 30 天

    ⚠️ 这里**不写 pydantic 的 ge/le 约束** —— 越界会直接返 422 + 一坨校验错误数组。
    改成交给 service 校验 → 返 400 + 一句中文（“有效期最长 30 天”），老师看得懂。
    """

    expire_hours: int = Field(default=168)


# ============================================================
# 管理线（要登录）
# ============================================================

@manage_router.post("/{paper_id}/shares")
def create_paper_share(
    paper_id: int,
    payload: ShareCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """给一张卷生成分享链接

    只有卷的主人能分享 —— 否则就能把别人的卷链接出去。
    """
    paper = session.get(Paper, paper_id)
    if not paper or paper.user_id != (current_user.id or 0):
        raise HTTPException(status_code=404, detail="试卷不存在")

    # 卷是空的就别分享了 —— 生成的链接打开是空白页，没意义
    detail = _paper_detail(paper, session)
    if not detail["questions"]:
        raise HTTPException(status_code=400, detail="试卷里还没有题目")

    try:
        record = create_share(current_user, paper, session, expire_hours=payload.expire_hours)
    except ShareError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _share_payload(record, paper)


@manage_router.get("/{paper_id}/shares")
def list_paper_shares(
    paper_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """列出这张卷的分享链接（含已过期 / 已吊销的，方便主人看清楚）"""
    paper = session.get(Paper, paper_id)
    if not paper or paper.user_id != (current_user.id or 0):
        raise HTTPException(status_code=404, detail="试卷不存在")

    records = list_shares(current_user, paper_id, session)
    return {
        "items": [_share_payload(r, paper) for r in records],
        "total": len(records),
    }


@manage_router.delete("/{paper_id}/shares/{share_id}")
def revoke_paper_share(
    paper_id: int,
    share_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """吊销一条分享链接

    链接作废后立刻打不开 —— 老师发现发错群了用这个。
    """
    paper = session.get(Paper, paper_id)
    if not paper or paper.user_id != (current_user.id or 0):
        raise HTTPException(status_code=404, detail="试卷不存在")

    record = get_share(share_id, current_user, session)
    if record is None or record.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="分享链接不存在")

    revoke_share(record, session)
    return {"revoked": True, "id": share_id}


# ============================================================
# 公开线（不用登录）
# ============================================================

@public_router.get("/{token}")
def view_shared_paper(
    token: str,
    session: Session = Depends(get_session),
):
    """看共享的卷子（只读）

    过期 / 吊销 / 不存在 —— 一律 404，不告诉访问者是哪一种。
    """
    record = resolve_share(token, session)
    if record is None:
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    paper = session.get(Paper, record.paper_id)
    if paper is None:
        # 卷被主人删了 → 链接自然失效
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    detail = _paper_detail(paper, session)

    touch_share(record, session)

    # ⚠️ 只返回卷的内容 —— 不带任何用户信息
    #    （不给 owner id / 用户名 / 邮箱等，公开接口一律不吐用户字段）
    return {
        "title": paper.title,
        "subtitle": paper.subtitle,
        "questions": [
            {
                "label": q["label"],
                "content_markdown": q["question"]["content_markdown"],
                "content_plain": q["question"]["content_plain"],
                "score": q["score"],
            }
            for q in detail["questions"]
        ],
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


@public_router.get("/{token}/export.pdf")
def export_shared_pdf(
    token: str,
    session: Session = Depends(get_session),
):
    """通过分享链接下 PDF"""
    record = resolve_share(token, session)
    if record is None:
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    paper = session.get(Paper, record.paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    detail = _paper_detail(paper, session)
    if not detail["questions"]:
        raise HTTPException(status_code=400, detail="试卷里还没有题目")

    items = _export_items(detail)

    try:
        pdf_bytes = export_paper_pdf(
            paper={"title": paper.title, "subtitle": paper.subtitle},
            items=items,
            trace=_share_trace(session, paper),
        )
    except PdfExportError as e:
        raise HTTPException(status_code=500, detail=str(e))

    from urllib.parse import quote
    filename = f"{paper.title}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"paper.pdf\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


@public_router.get("/{token}/export.jpg")
def export_shared_jpg(
    token: str,
    session: Session = Depends(get_session),
):
    """通过分享链接下 JPG（每页一张，打包 ZIP）"""
    record = resolve_share(token, session)
    if record is None:
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    paper = session.get(Paper, record.paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="链接不存在或已失效")

    detail = _paper_detail(paper, session)
    if not detail["questions"]:
        raise HTTPException(status_code=400, detail="试卷里还没有题目")

    items = _export_items(detail)

    try:
        pdf_bytes = export_paper_pdf(
            paper={"title": paper.title, "subtitle": paper.subtitle},
            items=items,
            trace=_share_trace(session, paper),
        )
        zip_bytes = build_jpg_zip(pdf_bytes, prefix=paper.title)
    except PdfExportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except JpgExportError as e:
        raise HTTPException(status_code=500, detail=str(e))

    from urllib.parse import quote
    filename = f"{paper.title}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"paper.zip\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


# ============================================================
# 辅助
# ============================================================

def _export_items(detail: dict) -> list[dict]:
    """导出用的题目数据（和 papers.py 同一份口径）

    用 markdown 版 → Chromium 里的 KaTeX 能渲染 $...$
    """
    items = []
    for item in detail["questions"]:
        q = item["question"]
        items.append({
            "label": item["label"],
            # ⚠️ 去掉【题图】占位符 —— 分享出去的卷子不该带内部标记
            "content": strip_figure_placeholder(
                q["content_markdown"] or q["content_plain"]
            ),
            "score": item["score"],
        })
    return items


def _share_trace(session: Session, paper: Paper) -> str:
    """分享链接导出时的溯源标记

    格式：试卷来源：{作者} | 试卷：{标题} | {时间}

    ⚠️ 跟本人导出用不同的措辞 —— 本人导出是「导出人」，分享下载是「试卷来源」。
    分享出去的卷子会落到别人手里，页脚写「导出人：某某老师」会让收卷子的学生
    以为是学生自己导出的；写「试卷来源」才是准确描述。
    """
    from datetime import datetime, timezone

    owner = session.get(User, paper.user_id)
    who = (owner.display_name or owner.username) if owner else "题库"
    when = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return f"试卷来源：{who} | 试卷：{paper.title} | {when}"


def _share_payload(record: PaperShare, paper: Paper) -> dict:
    """分享链接的返回体（管理线用）

    只回 token，完整 URL 由前端拼（前端知道自己的域名，
    后端拼 URL 要处理反代头，容易拼错）。
    """
    return {
        "id": record.id,
        "paper_id": record.paper_id,
        "paper_title": paper.title,
        "token": record.token,
        "state": share_state(record),
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        "view_count": record.view_count,
        "last_viewed_at": record.last_viewed_at.isoformat() if record.last_viewed_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
