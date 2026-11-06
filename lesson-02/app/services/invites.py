"""邀请码服务 — 课 34（灰度试用入口）

一条邀请码 = 「谁能注册 + 能注册几个 + 到什么时候」
--------------------------------------------------
灰度试用不是「所有人都能注册」—— 那等于开门营业。
邀请码是**闸门**：管理员发一批码出去，谁拿到码谁进得来，
进的人数和时限都有上限，出问题一键收回来。

四种失败要分开
--------------
| 情况 | code | 老师该做什么 |
|---|---|---|
| 码不存在 | invite.invalid | 找管理员要新码（可能输错了）|
| 码被停用 | invite.inactive | 找管理员（可能发了又收回）|
| 码过期 | invite.expired | 找管理员要新码（活动结束了）|
| 名额用完 | invite.exhausted | 找管理员加次数（同一批人太多）|

合成一句话的话，老师只能来问「为什么不能用」—— 分开才能自己判断该找谁。

名额怎么占
----------
``consume_invite`` 用**带条件的 UPDATE**（``used_count < max_uses``），
而不是「先查后加」——
两个老师同时用同一个码注册时，「先查后加」会让两个人都通过检查、名额却只加 1。
条件 UPDATE 由数据库保证：只有真的抢到名额的那一行才会被更新，
抢不到的行数是 0 → 报「名额已用完」。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, update
from sqlmodel import Session, select

from app.models import Invite
from app.services.errors import (
    CODE_INVITE_EXHAUSTED,
    CODE_INVITE_EXPIRED,
    CODE_INVITE_INACTIVE,
    CODE_INVITE_INVALID,
    ApiHTTPException,
)

# === 常量 ===

CODE_PREFIX = "TQB"

# 默认名额（一个人一个码）
DEFAULT_MAX_USES = 1

# 名额上限（防止「一个码发全校」）
MAX_MAX_USES = 100

# 默认有效期（天）
DEFAULT_EXPIRE_DAYS = 30

# 有效期上限（天）
MAX_EXPIRE_DAYS = 365


# === 邀请码 ===

def generate_code() -> str:
    """生成邀请码，形如 ``TQB-3A9F-2C71-B4D8``

    6 字节随机（48 位熵）+ 分组显示：
    - 熵：即使没有限流，暴力枚举也要天文数字次
    - 分组：老师念、抄、贴在群里不容易错位（纯 12 位连在一起容易看串）
    """
    raw = secrets.token_hex(6).upper()
    return f"{CODE_PREFIX}-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def normalize_code(code: str) -> str:
    """把老师输入的邀请码规整成库里的样子

    老师很可能从微信里复制，带空格 / 全角横线 / 大小写混着。
    统一转成大写、去掉空白再查 —— 否则「输对了却说码不存在」。
    """
    return (code or "").strip().upper().replace("－", "-").replace("—", "-")


def find_invite(session: Session, code: str) -> Optional[Invite]:
    """按码找邀请码，找不到返回 None"""
    normalized = normalize_code(code)
    if not normalized:
        return None
    return session.exec(
        select(Invite).where(Invite.code == normalized)
    ).first()


def assert_invite_usable(invite: Invite) -> None:
    """校验邀请码能不能用，不能用就抛对应机器码的错误

    顺序有意为之：**先看有没有被停用，再看过期，最后看名额** ——
    停用是管理员主动收权，优先级最高（过期了但又被停用，要提示停用）。
    """
    if not invite.is_active:
        raise ApiHTTPException(
            status_code=400,
            detail="邀请码已被停用，请联系管理员重新获取",
            code=CODE_INVITE_INACTIVE,
        )

    if invite.expires_at is not None and invite.expires_at <= datetime.now(timezone.utc):
        raise ApiHTTPException(
            status_code=400,
            detail="邀请码已过期，请联系管理员重新获取",
            code=CODE_INVITE_EXPIRED,
        )

    if invite.used_count >= invite.max_uses:
        raise ApiHTTPException(
            status_code=400,
            detail="邀请码名额已用完，请联系管理员增加次数",
            code=CODE_INVITE_EXHAUSTED,
        )


def consume_invite(session: Session, invite: Invite) -> None:
    """占用一个名额（**原子**）

    用带条件的 UPDATE，让「检查 + 占用」变成数据库里的一个原子动作：
    ``used_count < max_uses`` 不成立时更新 0 行 → 说明名额已被抢完。

    ⚠️ 不 commit —— 跟建用户放同一个事务里：
    后面建用户失败要回滚时，名额会一起退回去（老师不会「码用掉了却没注册上」）。
    """
    now = datetime.now(timezone.utc)
    stmt = (
        update(Invite)
        .where(
            Invite.id == invite.id,
            Invite.is_active.is_(True),
            Invite.used_count < Invite.max_uses,
            or_(Invite.expires_at.is_(None), Invite.expires_at > now),
        )
        .values(used_count=Invite.used_count + 1)
    )
    result = session.execute(stmt)
    if result.rowcount == 0:
        # 走到这里说明：校验之后、占用之前，别的请求把名额抢完了（并发）
        session.rollback()
        raise ApiHTTPException(
            status_code=400,
            detail="邀请码名额已用完，请联系管理员增加次数",
            code=CODE_INVITE_EXHAUSTED,
        )


def create_invite(
    session: Session,
    *,
    label: str = "",
    max_uses: int = DEFAULT_MAX_USES,
    expires_days: int = DEFAULT_EXPIRE_DAYS,
    created_by_user_id: Optional[int] = None,
) -> Invite:
    """建一个邀请码（管理员用）

    ``expires_days=0`` 表示**永不过期**。
    """
    if max_uses < 1:
        raise ValueError("名额至少为 1")
    if max_uses > MAX_MAX_USES:
        raise ValueError(f"名额最多 {MAX_MAX_USES}")
    if expires_days < 0:
        raise ValueError("有效期不能是负数")
    if expires_days > MAX_EXPIRE_DAYS:
        raise ValueError(f"有效期最多 {MAX_EXPIRE_DAYS} 天")

    expires_at = None
    if expires_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    invite = Invite(
        code=generate_code(),
        label=label.strip()[:50],
        max_uses=max_uses,
        used_count=0,
        expires_at=expires_at,
        is_active=True,
        created_by_user_id=created_by_user_id,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


def invite_state(invite: Invite) -> str:
    """邀请码当前状态（列表里给管理员看，一眼分辨）"""
    if not invite.is_active:
        return "disabled"
    if invite.expires_at is not None and invite.expires_at <= datetime.now(timezone.utc):
        return "expired"
    if invite.used_count >= invite.max_uses:
        return "exhausted"
    return "active"
