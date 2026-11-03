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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
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
