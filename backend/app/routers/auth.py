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

import os

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.services.audit import client_ip_and_port
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
    CODE_AUTH_ACCOUNT_NOT_FOUND,
    CODE_AUTH_INVALID_CREDENTIALS,
    CODE_AUTH_PHONE_TAKEN,
    CODE_AUTH_REGISTRATION_CLOSED,
    CODE_CONFLICT,
    CODE_FORBIDDEN,
    CODE_INVITE_INVALID,
    CODE_NOT_FOUND,
    CODE_PASSWORD_CHANGE_LOCKED,
    CODE_VALIDATION,
    ApiHTTPException,
)
from app.services.sms import (
    PURPOSE_REGISTER,
    PURPOSE_RESET,
    RESEND_INTERVAL_SECONDS,
    SMS_PURPOSES,
    mask_phone,
    normalize_phone,
    send_code,
    verify_code,
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
    """登录请求（lesson-39 · 账号 = 手机号，也兼容旧用户名）

    ⚠️ 两个字段都保留：新前端传 account（手机号），
    旧前端和脚本还在传 username —— 存量账号不能被这次改造锁在门外。
    """

    account: str = Field(default="", max_length=50)
    username: str = Field(default="", max_length=50)
    password: str = Field(max_length=128)


class SmsSendRequest(BaseModel):
    """发验证码请求（手机号 + 用途）

    purpose: register=注册（默认）/ reset=重置密码。
    不传按注册算 —— 老前端不受影响。
    """

    phone: str = Field(min_length=1, max_length=20)
    purpose: str = Field(default=PURPOSE_REGISTER, max_length=16)


class SmsSendResponse(BaseModel):
    """发码结果（cooldown = 前端倒计时秒数）"""

    sent: bool = True
    cooldown: int = 60


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class PasswordResetRequest(BaseModel):
    """手机号 + 验证码重置密码（lesson-40 · 老师忘记密码时用）

    ⚠️ 密码强度**不在** pydantic 里写（同注册）——
       弱密码要返一句中文（「至少一个大写字母」），不是一坨校验错误数组。
    """

    phone: str = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=12)
    new_password: str = Field(max_length=128)


class RegisterRequest(BaseModel):
    """手机号 + 验证码自助注册（lesson-39 · 替代邀请码注册）

    ⚠️ 密码强度**不在** pydantic 里写（不写 ge/le 约束）——
       弱密码要返一句中文（「至少一个大写字母」），不是一坨校验错误数组。
       长度上限在这里挡，超长密码直接拒绝（别拿 10MB 密码来占 CPU）。
    """

    phone: str = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=12)
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=50)


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

def _find_user_by_account(session: Session, ident: str) -> Optional[User]:
    """按账号找用户：先当手机号查，再当用户名查。

    为什么两条路都走
    --------------
    新体系里账号就是手机号（短信验证码证明「这个号是你的」）；
    但存量账号（test1 / 共享试用账号 / 早期老师）只有 username，没有 phone。
    两条都查，改造才不会把已经在用的老师挡在门外。

    顺序也有讲究：11 位数字先按 phone 查（那是新账号的真身份），
    查不到再按 username 查（老账号用户名恰好是数字的情况）。
    """
    ident = (ident or "").strip()
    if not ident:
        return None

    digits = normalize_phone(ident)
    if len(digits) == 11 and digits.startswith("1"):
        user = session.exec(select(User).where(User.phone == digits)).first()
        if user is not None:
            return user

    return session.exec(select(User).where(User.username == ident)).first()


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """账号密码登录（lesson-39 · 手机号就是账号）

    失败分两种，因为老师要做的事完全不同：

    - 账号不存在 → 「这个号还没注册」→ 前端引导去用验证码注册
    - 密码不对   → 「密码错了」→ 重输一次就行

    ⚠️ 这确实能被用来枚举已注册的手机号 —— 但现在注册是开放的
    （有手机号就能收验证码注册），枚举不出什么额外信息，可接受。
    """
    ident = (payload.account or payload.username or "").strip()
    if not ident:
        raise ApiHTTPException(
            status_code=400,
            detail="请输入手机号",
            code=CODE_VALIDATION,
        )

    user = _find_user_by_account(session, ident)

    # 用户不存在 → 也走一次哈希校验，抹平时间差
    if user is None:
        _dummy_verify(payload.password)
        raise ApiHTTPException(
            status_code=404,
            detail="账号不存在；如果用的是手机号，说明还没注册过",
            code=CODE_AUTH_ACCOUNT_NOT_FOUND,
        )

    if not verify_password(payload.password, user.password_hash):
        raise ApiHTTPException(
            status_code=401,
            detail="密码错了，再输一次",
            code=CODE_AUTH_INVALID_CREDENTIALS,
        )

    if not user.is_active:
        raise ApiHTTPException(
            status_code=403,
            detail="账号已被停用，请联系管理员",
            code=CODE_FORBIDDEN,
        )

    # 审计：这次登录的账号（失败的登录也会被记到账号上）
    request.state.user_id = user.id
    request.state.username = user.username

    # 签发会话
    client_ip, _client_port = client_ip_and_port(request)
    user_agent = request.headers.get("user-agent", "")
    token, record = create_session(
        user, session, ip=client_ip, user_agent=user_agent
    )

    # 记录登录时间
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)

    return LoginResponse(
        token=token,
        expires_in_days=SESSION_TTL_DAYS,
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


def _registration_open() -> bool:
    """注册通道开关。

    为什么要有这个开关
    ----------------
    邀请码时代的注册是**有闸的**：谁拿到码谁进得来。
    换短信注册后闸被拆了 —— 任何能收短信的手机号都能注册。
    站点是公开域名的老师工具，这个口子不该是「想开就开」，
    所以留一个环境变量：REGISTRATION_ENABLED=false 一键关掉，
    出事时改一行 + 重启就行，不用改代码发版。
    """
    return os.getenv("REGISTRATION_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


# === 短信验证码注册（lesson-39 · 替代邀请码注册） ===


@router.post("/sms/send", response_model=SmsSendResponse)
def send_sms_code(
    payload: SmsSendRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """发一条验证码短信（免登录）

    频控在服务层（services/sms.py）：同号 60 秒 1 条、每天 10 条、
    同 IP 每小时 20 条。拦在阿里云之前 —— 一次都别多花。

    已注册的手机号也允许发码（找回密码要用）。

    purpose 决定这次发的码干什么用：
    - register（默认）：注册
    - reset：重置密码 —— 这种码**只对已注册的号**发
    """
    # 通道关了就不发码 —— 免得白花钱（每条 0.06 元）
    if not _registration_open():
        raise ApiHTTPException(
            status_code=403,
            detail="注册通道暂时关闭，请联系管理员",
            code=CODE_AUTH_REGISTRATION_CLOSED,
        )

    purpose = (payload.purpose or PURPOSE_REGISTER).strip().lower()
    if purpose not in SMS_PURPOSES:
        raise ApiHTTPException(
            status_code=400,
            detail="验证码用途不对",
            code=CODE_VALIDATION,
        )

    if purpose == PURPOSE_RESET:
        # 改密只对已注册的号有意义 —— 没注册的号想「改密」，
        # 那其实是想注册，让前端引导去注册页签。
        phone = normalize_phone(payload.phone)
        found = session.exec(select(User).where(User.phone == phone)).first()
        if found is None:
            found = session.exec(select(User).where(User.username == phone)).first()
        if found is None:
            raise ApiHTTPException(
                status_code=404,
                detail="这个手机号还没注册过，没有密码可以重置",
                code=CODE_AUTH_ACCOUNT_NOT_FOUND,
            )

    client_ip, _client_port = client_ip_and_port(request)
    send_code(session, payload.phone, ip=client_ip, purpose=purpose)
    return SmsSendResponse(sent=True, cooldown=RESEND_INTERVAL_SECONDS)


@router.post("/register", response_model=LoginResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """手机号 + 验证码自助注册（lesson-39）

    流程：查重 → 验密码强度 → 阿里云核验验证码 → 建号 → 直接签发会话。

    为什么 username 直接填手机号
    ----------------------
    username 是 NOT NULL + UNIQUE —— 填手机号，唯一性天然成立，
    不用改表结构。而且老师登录时输入的就是它，两边对得上。

    注册成功**直接进首页**，不用再登一次（多一步就少一半人注册完就走了）。
    """
    if not _registration_open():
        raise ApiHTTPException(
            status_code=403,
            detail="注册通道暂时关闭，请联系管理员",
            code=CODE_AUTH_REGISTRATION_CLOSED,
        )

    phone = normalize_phone(payload.phone)
    if len(phone) != 11 or not phone.startswith("1"):
        raise ApiHTTPException(
            status_code=400,
            detail="手机号格式不对，检查一下",
            code=CODE_VALIDATION,
        )

    # 1. 这个号注册过没有（phone 列 + username 列都查：新账号 username 就是手机号）
    taken = session.exec(select(User).where(User.phone == phone)).first()
    if taken is None:
        taken = session.exec(select(User).where(User.username == phone)).first()
    if taken is not None:
        raise ApiHTTPException(
            status_code=409,
            detail="这个手机号已经注册过了，直接登录就行",
            code=CODE_AUTH_PHONE_TAKEN,
        )

    # 2. 密码强度（弱密码 → request.validation_failed）
    problems = check_password_strength(payload.password)
    if problems:
        raise ApiHTTPException(
            status_code=400,
            detail=f"密码不合规：{'；'.join(problems)}",
            code=CODE_VALIDATION,
        )

    # 3. 验证码核验（在阿里云那边比对 —— 我们不存明文码）
    client_ip, _client_port = client_ip_and_port(request)
    verify_code(session, phone, payload.code, ip=client_ip)

    # 4. 建用户 —— username 直接填手机号（唯一约束天然成立）
    user = User(
        username=phone,
        phone=phone,
        display_name=(payload.display_name or "").strip() or mask_phone(phone),
        password_hash=hash_password(payload.password),
        must_change_password=False,
        is_active=True,
        is_admin=False,
    )

    try:
        session.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiHTTPException(
            status_code=409,
            detail="这个手机号已经注册过了，直接登录就行",
            code=CODE_AUTH_PHONE_TAKEN,
        )

    session.refresh(user)

    # 审计：这次注册的账号
    request.state.user_id = user.id
    request.state.username = user.username

    # 5. 签发会话（跟登录一样，前端注册完直接进首页）
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
            must_change_password=user.must_change_password,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            is_admin=user.is_admin,
            allow_password_change=user.allow_password_change,
        ),
    )


# === 忘记密码：手机号 + 验证码重置（lesson-40）===


@router.post("/password/reset", response_model=LoginResponse)
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """手机号 + 验证码重置密码（lesson-40 · 老师忘记密码时用）

    流程：查号 → 验新密码强度 → 阿里云核验验证码 → 改密码 →
    踢掉所有旧会话 → 签发新会话。

    ⚠️ 为什么改完踢掉**所有**会话（不像「修改密码」只踢其他设备）
    ------------------------------------------------------
    忘密码的场景下，**不能排除**是别人拿着手机把密码改了。
    旧会话必须全清 —— 不然那个人还能继续用这个账号。
    """
    phone = normalize_phone(payload.phone)
    if len(phone) != 11 or not phone.startswith("1"):
        raise ApiHTTPException(
            status_code=400,
            detail="手机号格式不对，检查一下",
            code=CODE_VALIDATION,
        )

    user = session.exec(select(User).where(User.phone == phone)).first()
    if user is None:
        user = session.exec(select(User).where(User.username == phone)).first()
    if user is None:
        raise ApiHTTPException(
            status_code=404,
            detail="这个手机号还没注册过，没有密码可以重置",
            code=CODE_AUTH_ACCOUNT_NOT_FOUND,
        )

    # 共享试用账号不给自助改密 —— 改一个所有人掉线（跟 change-password 一样）
    if not user.allow_password_change:
        raise ApiHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账号是共享试用账号，需要改请联系管理员",
            code=CODE_PASSWORD_CHANGE_LOCKED,
        )

    # 密码强度 —— 和注册同一套规矩
    problems = check_password_strength(payload.new_password)
    if problems:
        raise ApiHTTPException(
            status_code=400,
            detail=f"新密码不合规：{'；'.join(problems)}",
            code=CODE_VALIDATION,
        )

    # 验证码核验 —— 用途必须是「重置密码」，注册用的码在这里会被拒
    client_ip, _client_port = client_ip_and_port(request)
    verify_code(session, phone, payload.code, ip=client_ip, purpose=PURPOSE_RESET)

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    session.add(user)
    session.commit()

    # 旧会话全清（忘密码 = 可能被别人改了，别留后门）
    revoke_all_sessions(session, user.id or 0)

    # 签发新会话 —— 改完直接进首页，不用再登一次
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
            must_change_password=user.must_change_password,
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
