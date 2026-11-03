"""认证服务 — lesson-11 用户体系

三块职责
--------
1. **密码哈希与校验**（bcrypt）
2. **会话签发与校验**（服务端 Session，token 存哈希不存明文）
3. **当前用户依赖注入**（路由层用 ``Depends(get_current_user)`` 拿登录用户）

为什么 Session 存服务端而不是无状态 token
------------------------------------------
备案要求「管理员可随时停用及封禁特定账号」—— 无状态 token 做不到立即失效，
封号后旧 token 还能用到过期。服务端 Session 删一行就踢下线。

token 为什么不存明文
-------------------
数据库被拖走时，存明文 token = 攻击者直接拿到可用凭证。
只存哈希（sha256）—— 校验时对传入 token 做同样哈希再比对，
数据库里没有能直接用的凭证。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import Session_, User

# ============ 常量 ============

# 会话有效期（天）
SESSION_TTL_DAYS = 7

# 空闲多久自动失效（天）—— 老师一周没登录就自动掉线
SESSION_IDLE_DAYS = 30

# 密码强度规则（和建号脚本一致）
_PASSWORD_RULES = (
    (lambda s: any(c.islower() for c in s), "至少一个小写字母"),
    (lambda s: any(c.isupper() for c in s), "至少一个大写字母"),
    (lambda s: any(c.isdigit() for c in s), "至少一个数字"),
)


# ============ 密码 ============

def check_password_strength(password: str) -> list[str]:
    """返回密码不合规的原因列表，空列表 = 通过

    规则：大小写字母 + 数字 + ≥8 位。不强制特殊符号 ——
    老师容易忘，强度已经够了。
    """
    problems: list[str] = []

    if len(password) < 8:
        problems.append(f"长度不足 8 位（当前 {len(password)} 位）")

    for check, message in _PASSWORD_RULES:
        if not check(password):
            problems.append(message)

    return problems


def hash_password(password: str) -> str:
    """bcrypt 哈希（自带 salt）"""
    import bcrypt

    # bcrypt 只看前 72 字节，显式截断让行为可预期
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码

    哈希格式不对（库里存了脏数据）时抛异常 —— 不当成「密码错误」，
    否则用户永远不知道自己密码是对的还是系统坏了。
    """
    import bcrypt

    raw = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        raise RuntimeError("密码哈希格式损坏，需要人工检查")


# ============ 会话 ============

def _hash_token(token: str) -> str:
    """token → sha256 十六进制（64 字符）

    用 sha256 而不是 bcrypt：token 本身已是 256 位随机数，
    不需要防爆破；这里要的是「不可逆 + 查得快」。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    user: User,
    session: Session,
    *,
    ip: str = "",
    user_agent: str = "",
) -> tuple[str, Session_]:
    """给用户签发一个会话，返回 (明文 token, 会话记录)

    明文 token **只在这里出现一次** —— 存进库的是哈希。
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    record = Session_(
        user_id=user.id or 0,
        token_hash=_hash_token(token),
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        last_used_at=now,
        ip=ip[:45],
        user_agent=user_agent[:300],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return token, record


def get_session_by_token(token: str, session: Session) -> Optional[Session_]:
    """按 token 找会话，已失效返回 None"""
    if not token:
        return None

    record = session.exec(
        select(Session_).where(Session_.token_hash == _hash_token(token))
    ).first()
    if record is None:
        return None

    now = datetime.now(timezone.utc)

    # 过期了 —— 顺手删掉（省得定时任务来清）
    if record.expires_at <= now:
        session.delete(record)
        session.commit()
        return None

    # 空闲太久 —— 也失效
    idle_limit = now - timedelta(days=SESSION_IDLE_DAYS)
    if record.last_used_at < idle_limit:
        session.delete(record)
        session.commit()
        return None

    return record


def revoke_session(session: Session, record: Session_) -> None:
    """注销一个会话"""
    session.delete(record)
    session.commit()


def revoke_all_sessions(session: Session, user_id: int) -> int:
    """注销某用户的全部会话（改密码后调用 —— 踢掉其他设备）

    返回被注销的会话数。
    """
    records = session.exec(
        select(Session_).where(Session_.user_id == user_id)
    ).all()
    for record in records:
        session.delete(record)
    session.commit()
    return len(records)


def purge_expired_sessions(session: Session) -> int:
    """清理过期会话，返回清理条数"""
    now = datetime.now(timezone.utc)
    records = session.exec(
        select(Session_).where(Session_.expires_at <= now)
    ).all()
    for record in records:
        session.delete(record)
    session.commit()
    return len(records)


# ============ 当前用户 ============

def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """FastAPI 依赖：拿当前登录用户，未登录直接 401

    token 从 ``Authorization: Bearer <token>`` 取。
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = header[7:].strip()
    record = get_session_by_token(token, session)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session.get(User, record.user_id)
    if user is None:
        # 会话指向的用户没了（被删）—— 清掉这条会话
        session.delete(record)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在",
        )

    if not user.is_active:
        # 账号被停用（软删除）—— 立刻踢下线
        revoke_all_sessions(session, user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用",
        )

    # 顺手更新活跃时间（不用每次 commit，省一次写）
    record.last_used_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()

    return user


def get_optional_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """FastAPI 依赖：拿当前登录用户，没登录返回 None（不报错）

    用于「登录与否都能访问，但登录后行为不同」的接口。
    """
    try:
        return get_current_user(request, session)
    except HTTPException:
        return None
