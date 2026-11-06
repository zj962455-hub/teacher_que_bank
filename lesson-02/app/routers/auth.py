"""认证路由 — lesson-11 用户体系

对应前端
--------
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /api/auth/login | 用户名密码登录，签发会话 |
| POST | /api/auth/register | 邀请码自助注册（课 34），注册完直接签发会话 |
| POST | /api/auth/logout | 注销当前会话 |
| POST | /api/auth/change-password | 修改密码（改完踢掉其他设备）|
| GET  | /api/auth/me | 当前登录用户信息 |
| GET  | /api/auth/invites | 邀请码列表（**仅管理员**）|
| POST | /api/auth/invites | 生成邀请码（**仅管理员**）|
| PATCH | /api/auth/invites/{id} | 启停/改名额（**仅管理员**）|

登录流程
--------
1. 查用户 → 2. 校验密码 → 3. 更新 last_login_at → 4. 签发 session → 5. 返回明文 token

注册流程（课 34）
----------------
1. 验邀请码（不存在/停用/过期/用尽，各有各的机器码）
2. 查用户名是否重复 → 3. 验密码强度 → 4. 建用户 → 5. 占用邀请码名额 → 6. 签发 session
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Invite, Question, Paper, Session_, Upload, User
from app.services.auth import (
    SESSION_TTL_DAYS,
    check_password_strength,
    create_session,
    get_current_user,
    hash_password,
    require_admin,
    revoke_all_sessions,
    revoke_session,
    verify_password,
)
from app.services.errors import (
    CODE_CONFLICT,
    CODE_INVITE_INVALID,
    CODE_NOT_FOUND,
    CODE_PASSWORD_CHANGE_LOCKED,
    CODE_VALIDATION,
    ApiHTTPException,
)
from app.services.invites import (
    DEFAULT_EXPIRE_DAYS,
    DEFAULT_MAX_USES,
    MAX_EXPIRE_DAYS,
    MAX_MAX_USES,
    assert_invite_usable,
    consume_invite,
    create_invite,
    find_invite,
    invite_state,
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


class RegisterRequest(BaseModel):
    """邀请码自助注册（课 34 · 灰度试用入口）

    ⚠️ 密码强度**不在** pydantic 里写（不写 ge/le 约束）——
       弱密码要返一句中文（「至少一个大写字母」），不是一坨校验错误数组。
       长度上限在这里挡，超长密码直接拒绝（别拿 10MB 密码来占 CPU）。
    """

    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=50)
    invite_code: str = Field(min_length=1, max_length=32)


class InviteCreateRequest(BaseModel):
    """生成邀请码（管理员）"""

    label: str = Field(default="", max_length=50)
    max_uses: int = Field(default=DEFAULT_MAX_USES)
    # 0 = 永不过期
    expires_days: int = Field(default=DEFAULT_EXPIRE_DAYS)


class InviteUpdateRequest(BaseModel):
    """改邀请码（管理员）：停用/启用、改名额、改备注

    全是可选 —— 只传要改的字段。
    """

    label: Optional[str] = Field(default=None, max_length=50)
    max_uses: Optional[int] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)


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
    # 管理员标记（课 34）—— 前端据此显示管理员入口（邀请码管理 / 全部反馈）
    is_admin: bool = False
    # 能不能自助改密码（课 34 · 共享试用账号锁死）
    # ⚠️ 前端据此隐藏改密表单 —— 但**真正的门在后端**（改密接口自己 403）。
    allow_password_change: bool = True


class InviteOut(BaseModel):
    """邀请码（管理员视角）

    ⚠️ ``code`` 明文返回给管理员
    ----------------------------
    理由跟 ``paper_shares.token`` 一样：**要能反复复制分发**。
    管理员要把码发微信、贴群公告、印在通知里 —— 存哈希就永远拿不回原文，
    只能作废重发，那不叫邀请码，叫一次性口令。

    它不是密码级秘密：
    - 6 字节随机（48 位熵），猜不中
    - 名额有限，用完即废
    - 可停用、可过期
    - **只有管理员看得到**（接口层面 require_admin 挡着，普通用户拿不到）
    泄露的最坏后果 = 多注册一个账号，不是「拿到别人的数据」。
    """

    id: int
    code: str
    label: str
    max_uses: int
    used_count: int
    remaining: int
    expires_at: str | None = None
    is_active: bool
    state: str
    created_at: str | None = None


class InviteListOut(BaseModel):
    items: list[InviteOut]
    total: int


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
            is_admin=user.is_admin,
            allow_password_change=user.allow_password_change,
        ),
    )


# === 注册（邀请码自助） ===

@router.post("/register", response_model=LoginResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """邀请码自助注册（课 34 · 灰度试用入口）

    注册成功**直接签发会话**返回 token —— 老师填完表就进首页，
    不用再登一次（多一步就少一半人注册完就走了）。
    """
    # 1. 邀请码：不存在 / 停用 / 过期 / 用尽 —— 四种情况各有各的机器码
    invite = find_invite(session, payload.invite_code)
    if invite is None:
        raise ApiHTTPException(
            status_code=400,
            detail="邀请码不存在，请检查是否输错",
            code=CODE_INVITE_INVALID,
        )
    assert_invite_usable(invite)

    # 2. 用户名唯一
    username = payload.username.strip()
    if not username:
        raise ApiHTTPException(
            status_code=400,
            detail="请填写用户名",
            code=CODE_VALIDATION,
        )
    if session.exec(select(User).where(User.username == username)).first() is not None:
        raise ApiHTTPException(
            status_code=409,
            detail="该用户名已被注册，换一个试试",
            code=CODE_CONFLICT,
        )

    # 3. 密码强度（弱密码 → request.validation_failed）
    problems = check_password_strength(payload.password)
    if problems:
        raise ApiHTTPException(
            status_code=400,
            detail=f"密码不合规：{'；'.join(problems)}",
            code=CODE_VALIDATION,
        )

    # 4. 建用户 —— 老师自己定的密码，不用强制改密
    user = User(
        username=username,
        display_name=(payload.display_name or "").strip() or username,
        password_hash=hash_password(payload.password),
        must_change_password=False,
        is_active=True,
        is_admin=False,
    )

    # 5. 建用户 + 占用邀请码名额：**同一个事务**
    #    名额占用失败 → 用户也不落库（老师不会「码用掉了却没注册上」）
    try:
        session.add(user)
        session.flush()
        consume_invite(session, invite)
        session.commit()
    except ApiHTTPException:
        session.rollback()
        raise
    except IntegrityError:
        # 并发注册同名用户 → 唯一索引拦下来了
        session.rollback()
        raise ApiHTTPException(
            status_code=409,
            detail="该用户名已被注册，换一个试试",
            code=CODE_CONFLICT,
        )

    session.refresh(user)

    # 6. 签发会话（跟登录一样，前端注册完直接进首页）
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    token, _record = create_session(
        user, session, ip=client_ip, user_agent=user_agent
    )

    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()

    return LoginResponse(
        token=token,
        expires_in_days=SESSION_TTL_DAYS,
        user=UserOut(
            id=user.id or 0,
            username=user.username,
            display_name=user.display_name,
            must_change_password=False,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            is_admin=user.is_admin,
            allow_password_change=user.allow_password_change,
        ),
    )


# === 邀请码管理（仅管理员） ===

@router.get("/invites", response_model=InviteListOut)
def list_invites(
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """邀请码列表（管理员）

    只返回码**自己的**信息（码/备注/名额/过期/状态）——
    不带创建者的用户名：这条接口只需要回答「有哪些码、还能不能用」，
    多带一个创建者字段没意义，还多漏一个信息。
    """
    records = session.exec(
        select(Invite).order_by(Invite.created_at.desc()).limit(200)
    ).all()
    items = [_invite_out(r) for r in records]
    return {"items": items, "total": len(items)}


@router.post("/invites", response_model=InviteOut)
def create_invite_endpoint(
    payload: InviteCreateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """生成邀请码（管理员）

    返回体里带明文 code —— **只有这一次**能拿到可分发的码
    （列表里也能看到，但那是给管理员自己核对用的）。
    """
    try:
        invite = create_invite(
            session,
            label=payload.label,
            max_uses=payload.max_uses,
            expires_days=payload.expires_days,
            created_by_user_id=admin.id,
        )
    except ValueError as e:
        raise ApiHTTPException(
            status_code=400,
            detail=str(e),
            code=CODE_VALIDATION,
        )
    return _invite_out(invite)


@router.patch("/invites/{invite_id}", response_model=InviteOut)
def update_invite(
    invite_id: int,
    payload: InviteUpdateRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """改邀请码：停用/启用、改名额、改备注（管理员）

    停用后老师拿这个码注册会收到「邀请码已被停用」——
    比「邀请码不存在」诚实：老师知道自己拿过码。
    """
    invite = session.get(Invite, invite_id)
    if invite is None:
        raise ApiHTTPException(
            status_code=404,
            detail="邀请码不存在",
            code=CODE_NOT_FOUND,
        )

    if payload.label is not None:
        invite.label = payload.label.strip()[:50]

    if payload.max_uses is not None:
        if payload.max_uses < 1:
            raise ApiHTTPException(
                status_code=400,
                detail="名额至少为 1",
                code=CODE_VALIDATION,
            )
        if payload.max_uses > MAX_MAX_USES:
            raise ApiHTTPException(
                status_code=400,
                detail=f"名额最多 {MAX_MAX_USES}",
                code=CODE_VALIDATION,
            )
        invite.max_uses = payload.max_uses

    if payload.is_active is not None:
        invite.is_active = payload.is_active

    session.add(invite)
    session.commit()
    session.refresh(invite)
    return _invite_out(invite)


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

    ⚠️ 共享试用账号（allow_password_change=false）直接 403
    ------------------------------------------------------
    灰度阶段几个老师**共用一个账号** —— 改密码会 revoke_all_sessions，
    **一个人改密 = 所有人被踢下线**（改密的那位自己也一起掉线）。
    所以这类账号不给改密，要改找管理员。
    """
    if not user.allow_password_change:
        raise ApiHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "该账号是共享试用账号，改密码会把其他老师一起踢下线，"
                "需要改请联系管理员。"
            ),
            code=CODE_PASSWORD_CHANGE_LOCKED,
        )

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
        is_admin=user.is_admin,
        allow_password_change=user.allow_password_change,
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
        is_admin=user.is_admin,
        allow_password_change=user.allow_password_change,
    )


# === 辅助 ===

def _invite_out(invite: Invite) -> InviteOut:
    """邀请码 → 返回体

    ``remaining`` 直接算好给前端（前端不该自己算 max-used）。
    """
    return InviteOut(
        id=invite.id or 0,
        code=invite.code,
        label=invite.label,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        remaining=max(0, invite.max_uses - invite.used_count),
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        is_active=invite.is_active,
        state=invite_state(invite),
        created_at=invite.created_at.isoformat() if invite.created_at else None,
    )

def _dummy_verify(password: str) -> None:
    """用户不存在时也跑一次 bcrypt，抹平响应时间差（防用户名枚举）"""
    import bcrypt

    try:
        bcrypt.checkpw(password.encode("utf-8")[:72], b"$2b$12$" + b"." * 53)
    except Exception:
        pass
