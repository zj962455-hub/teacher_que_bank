"""分享链接服务 — lesson-24

一张卷子 → 一个（或多个）带过期时间的公开链接
--------------------------------------------
老师组完卷，点「生成分享链接」→ 链接发到微信群 / 学生家长 →
对方点开在浏览器里直接看卷子、下 PDF / JPG，**不需要账号**。

这节课的核心是「带过期时间」
---------------------------
链接一旦发出去就收不回来了（可能已进群存档、已转发给第三方）。
所以每条链接必须有明确的失效时间，且能随时吊销 —— 没有「永久链接」这个选项。

三种失效方式
------------
| 方式 | 判据 |
|---|---|
| 过期 | ``expires_at <= now`` |
| 吊销 | ``revoked_at`` 非空 |
| 主人删卷 | 卷没了 → 链接自然也失效（外键级联/查询时找不到卷） |

安全边界
--------
分享链接是**唯一一条对外暴露题目内容的口子**，所以：
- 只读：只能看这一张卷，不能改、不能列出别的卷、拿不到账号
- 限时：默认 7 天，最多 30 天
- 可吊销：主人随时能让链接失效
- 不可枚举：token 是 32 字节 URL-safe 随机数（256 位熵），猜不出来
- 有审计：每次访问记 ``view_count`` / ``last_viewed_at``

token 明文存的取舍
------------------
会话 token 存哈希（因为会话等价于「账号本身」）。分享链接不这么做 ——
老师要能**反复复制同一个链接**（这周班级群、下周补课群），存哈希就拿不回原文了。
它的泄露面也小得多：只值一张卷的只读查看，且限时 + 可吊销。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.models import Paper, PaperShare, User

# === 默认与上限 ===

# 默认有效期（小时）= 7 天
DEFAULT_EXPIRE_HOURS = 168

# 最长有效期（小时）= 30 天
MAX_EXPIRE_HOURS = 720

# 最短有效期（小时）= 1 小时（防手滑生成「马上失效」的链接）
MIN_EXPIRE_HOURS = 1


class ShareError(Exception):
    """分享链接操作失败"""


def generate_token() -> str:
    """生成链接凭证

    32 字节 → ``secrets.token_urlsafe`` 出来 43 个字符，全是 URL-safe 的
    （A-Za-z0-9_-），不用再 urlencode，放进链接里不会转义坏掉。
    """
    return secrets.token_urlsafe(32)


def create_share(
    user: User,
    paper: Paper,
    session: Session,
    *,
    expire_hours: int = DEFAULT_EXPIRE_HOURS,
) -> PaperShare:
    """给一张卷创建分享链接

    Args:
        user: 当前登录用户（必须是卷的主人）
        paper: 要分享的卷
        expire_hours: 有效小时数，落在 [1, 720]

    Raises:
        ShareError: 有效期不合法
    """
    if expire_hours < MIN_EXPIRE_HOURS:
        raise ShareError(f"有效期至少 {MIN_EXPIRE_HOURS} 小时")
    if expire_hours > MAX_EXPIRE_HOURS:
        raise ShareError(f"有效期最长 {MAX_EXPIRE_HOURS // 24} 天")

    now = datetime.now(timezone.utc)
    record = PaperShare(
        user_id=user.id or 0,
        paper_id=paper.id or 0,
        token=generate_token(),
        expires_at=now + timedelta(hours=expire_hours),
        view_count=0,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_shares(user: User, paper_id: int, session: Session) -> list[PaperShare]:
    """列出某张卷（属于该用户）的所有分享链接

    按创建时间倒序 —— 老师通常先看最近生成的那条。
    """
    return list(
        session.exec(
            select(PaperShare)
            .where(PaperShare.user_id == (user.id or 0))
            .where(PaperShare.paper_id == paper_id)
            .order_by(PaperShare.created_at.desc())
        ).all()
    )


def get_share(share_id: int, user: User, session: Session) -> Optional[PaperShare]:
    """取某条分享链接（限本人）"""
    record = session.get(PaperShare, share_id)
    if record is None or record.user_id != (user.id or 0):
        return None
    return record


def revoke_share(record: PaperShare, session: Session) -> None:
    """吊销一条分享链接

    用「标记 revoked_at」而不是删行 —— 保留审计痕迹：
    备案要能回答「这条链接什么时候被作废的」。
    """
    record.revoked_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()


def resolve_share(token: str, session: Session) -> Optional[PaperShare]:
    """按 token 找有效链接（公开访问入口）

    过期 / 吊销 / 不存在 —— **一律返回 None**，不给访问者区分原因
    （区分了等于告诉别人「这个链接曾经存在」，多给一点信息量，少一点安全性）。
    """
    if not token:
        return None

    record = session.exec(
        select(PaperShare).where(PaperShare.token == token)
    ).first()
    if record is None:
        return None

    if record.revoked_at is not None:
        return None

    if record.expires_at <= datetime.now(timezone.utc):
        return None

    return record


def touch_share(record: PaperShare, session: Session) -> None:
    """记一次访问（审计）"""
    record.view_count = (record.view_count or 0) + 1
    record.last_viewed_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()


def share_state(record: PaperShare) -> str:
    """链接当前状态（给主人看的列表用）

    有效 / 已过期 / 已吊销
    """
    if record.revoked_at is not None:
        return "revoked"
    if record.expires_at <= datetime.now(timezone.utc):
        return "expired"
    return "active"
