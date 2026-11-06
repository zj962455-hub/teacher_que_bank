"""认证路由 — lesson-11 用户体系

对应前端
--------
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /api/auth/login | 用户名密码登录，签发会话 |
| POST | /api/auth/logout | 注销当前会话 |
| POST | /api/auth/change-password | 修改密码（改完踢掉其他设备）|
| GET  | /api/auth/me | 当前登录用户信息 |

登录流程
--------
1. 查用户 → 2. 校验密码 → 3. 更新 last_login_at → 4. 签发 session → 5. 返回明文 token
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Question, Paper, Session_, Upload, User
from app.services.auth import (
    check_password_strength,
    create_session,
    get_current_user,
    hash_password,
    revoke_all_sessions,
    revoke_session,
    verify_password,
)

router = APIRouter(
    prefix="/auth",
    tags=["认证"],
)


# === 请求体 / 响应体 ===

class LoginRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class UpdateProfileRequest(BaseModel):
    """修改个人资料

    目前只开放显示名 —— 用户名是登录凭据,改了会导致
    账号历史对不上（溯源串、审计日志都记着旧用户名）,所以不开放改。
    """
    display_name: str = Field(default="", max_length=50)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    must_change_password: bool
    last_login_at: str | None = None


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in_days: int
    user: UserOut


# === 登录 ===

@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """用户名密码登录

    失败一律返回 401 + 统一文案 —— 不区分「用户不存在」和「密码错」，
    避免被拿来枚举账号。
    """
    user = session.exec(
        select(User).where(User.username == payload.username)
    ).first()

    # 用户不存在 → 也走一次哈希校验，抹平时间差（防用户名枚举）
    if user is None:
        _dummy_verify(payload.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用，请联系管理员",
        )

    # 签发会话
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    token, record = create_session(
        user, session, ip=client_ip, user_agent=user_agent
    )

    # 记录登录时间
    from datetime import datetime, timezone

    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)

    return LoginResponse(
        token=token,
        expires_in_days=7,
        user=UserOut(
            id=user.id or 0,
            username=user.username,
            display_name=user.display_name,
            must_change_password=user.must_change_password,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        ),
    )


# === 注销 ===

@router.post("/logout")
def logout(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """注销当前会话"""
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else ""

    from app.services.auth import get_session_by_token

    record = get_session_by_token(token, session)
    if record is not None:
        revoke_session(session, record)

    return {"ok": True}


# === 修改密码 ===

@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """修改密码

    改完把该用户**其他设备**的会话全踢掉（当前这个保留）。
    """
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="原密码错误",
        )

    if payload.old_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与原密码相同",
        )

    problems = check_password_strength(payload.new_password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"新密码不合规：{'；'.join(problems)}",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    session.add(user)
    session.commit()

    # 踢掉其他设备的会话
    revoked = revoke_all_sessions(session, user.id or 0)

    return {
        "ok": True,
        "message": "密码已修改",
        "revoked_sessions": revoked,
    }


# === 个人中心 ===

@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: UpdateProfileRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """修改个人资料（目前只支持显示名）"""
    display_name = payload.display_name.strip()
    if len(display_name) > 50:
        raise HTTPException(status_code=400, detail="显示名最长 50 字")

    user.display_name = display_name
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserOut(
        id=user.id or 0,
        username=user.username,
        display_name=user.display_name,
        must_change_password=False,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.get("/stats")
def my_stats(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """我的数据统计（个人中心展示用）

    只统计当前用户自己的 —— 与列表接口同一套隔离口径。
    """
    from sqlalchemy import func

    uid = user.id or 0

    # ⚠️ 课 33 性能：原来三个计数都是 `len(session.exec(select(X).where(...)).all())`
    #    —— 把**整表**拉进 Python 再 len()。
    #    题库几千道题时,打开仪表盘就是把题目全查一遍再扔掉。
    #    正确做法：COUNT 交给数据库,只回一个数字。
    question_count = session.exec(
        select(func.count()).select_from(Question).where(Question.user_id == uid)
    ).one()

    paper_count = session.exec(
        select(func.count()).select_from(Paper).where(Paper.user_id == uid)
    ).one()

    upload_count = session.exec(
        select(func.count()).select_from(Upload).where(Upload.user_id == uid)
    ).one()

    # 题目按学科分组
    rows = session.exec(
        select(Question.subject, func.count())
        .where(Question.user_id == uid)
        .group_by(Question.subject)
    ).all()

    return {
        "questions": question_count,
        "papers": paper_count,
        "uploads": upload_count,
        "by_subject": [{"subject": s, "count": c} for s, c in rows],
    }


@router.get("/sessions")
def my_sessions(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """我的登录会话（个人中心展示用）

    让用户看到「现在有哪几台设备登着我的账号」——
    这是「可单独停用及封禁」的一部分。
    """
    records = session.exec(
        select(Session_)
        .where(Session_.user_id == (user.id or 0))
        .order_by(Session_.last_used_at.desc())
    ).all()

    now = datetime.now(timezone.utc)
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "last_used_at": r.last_used_at.isoformat(),
            "expires_at": r.expires_at.isoformat(),
            "ip": r.ip,
            "user_agent": r.user_agent[:120],
            "expired": r.expires_at <= now,
        }
        for r in records
    ]


@router.delete("/sessions/{session_id}")
def revoke_session_by_id(
    session_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """注销某个会话（自己踢自己别的设备）"""
    record = session.get(Session_, session_id)
    if record is None or record.user_id != (user.id or 0):
        raise HTTPException(status_code=404, detail="会话不存在")

    session.delete(record)
    session.commit()
    return {"ok": True, "revoked": session_id}


# === 当前用户 ===

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """当前登录用户信息"""
    return UserOut(
        id=user.id or 0,
        username=user.username,
        display_name=user.display_name,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


# === 辅助 ===

def _dummy_verify(password: str) -> None:
    """用户不存在时也跑一次 bcrypt，抹平响应时间差（防用户名枚举）"""
    import bcrypt

    try:
        bcrypt.checkpw(password.encode("utf-8")[:72], b"$2b$12$" + b"." * 53)
    except Exception:
        pass
