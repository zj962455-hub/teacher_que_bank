"""邀请码自助注册测试 — 课 34（灰度试用入口）

覆盖：
- 注册成功并自动登录（直接拿到 token，/me 能用）
- 邀请码四种失败：不存在 / 已停用 / 已过期 / 已用尽（各自机器码）
- 用户名重复 → resource.conflict
- 弱密码 → request.validation_failed
- 邀请码名额用一次加一次
- 管理接口：只有管理员能调（普通用户 403、未登录 401）
- 管理接口：生成 / 列表 / 停用 / 改名额

跑法：
    cd lesson-02
    venv/bin/python -m pytest tests/test_invites.py -v
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Invite, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "Test1234"
STRONG_PASSWORD = "Abc12345"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清干净数据

    ⚠️ 显式 SQL 按外键顺序删 —— invites / feedbacks 引用 users，
       先删它们再删 users（虽然有 ON DELETE CASCADE，显式更清楚）。
    """
    with Session(engine) as session:
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM feedbacks",
            "DELETE FROM invites",
            "DELETE FROM uploads",
            "DELETE FROM paper_shares",
            "DELETE FROM paper_questions",
            "DELETE FROM papers",
            "DELETE FROM question_tags",
            "DELETE FROM tags",
            "DELETE FROM questions",
            "DELETE FROM categories",
            "DELETE FROM users",
        ):
            session.exec(text(sql))
        session.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


# === 辅助 ===

def _make_user(username: str, *, is_admin: bool = False, password: str = PASSWORD) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=username,
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _make_invite(
    *,
    code: str = "TQB-TEST-CODE-0001",
    label: str = "测试批次",
    max_uses: int = 1,
    used_count: int = 0,
    expires_at=None,
    is_active: bool = True,
    created_by_user_id=None,
) -> int:
    with Session(engine) as session:
        invite = Invite(
            code=code,
            label=label,
            max_uses=max_uses,
            used_count=used_count,
            expires_at=expires_at,
            is_active=is_active,
            created_by_user_id=created_by_user_id,
        )
        session.add(invite)
        session.commit()
        session.refresh(invite)
        return invite.id or 0


def _login(client, username: str = "test1", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _h(token: str):
    return {"Authorization": f"Bearer {token}"}


def _register(client, **kwargs):
    payload = {
        "username": "newteacher",
        "password": STRONG_PASSWORD,
        "display_name": "新老师",
        "invite_code": "TQB-TEST-CODE-0001",
    }
    payload.update(kwargs)
    return client.post("/api/auth/register", json=payload)


# ============================================================
# 注册
# ============================================================

def test_register_success_and_auto_login(client):
    """注册成功 → 直接拿到 token，/me 能用（不用再登一次）"""
    _make_invite()

    resp = _register(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"], "注册成功就应该签发会话"
    assert data["user"]["username"] == "newteacher"
    assert data["user"]["display_name"] == "新老师"
    # 自己定的密码 → 不用强制改密
    assert data["user"]["must_change_password"] is False
    assert data["user"]["is_admin"] is False

    # token 真的能用
    me = client.get("/api/auth/me", headers=_h(data["token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "newteacher"


def test_register_user_is_active_and_not_admin(client):
    _make_invite()
    _register(client)
    with Session(engine) as session:
        from sqlmodel import select

        user = session.exec(select(User).where(User.username == "newteacher")).first()
        assert user is not None
        assert user.is_active is True
        assert user.is_admin is False
        assert user.password_hash != STRONG_PASSWORD, "密码不能明文存"


def test_register_consumes_invite_count(client):
    """注册成功 → 名额用掉一个"""
    invite_id = _make_invite(max_uses=2)
    _register(client)
    with Session(engine) as session:
        invite = session.get(Invite, invite_id)
        assert invite.used_count == 1


def test_register_invite_not_found(client):
    """邀请码不存在 → invite.invalid"""
    resp = _register(client, invite_code="TQB-NOT-EXIST-0001")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "invite.invalid"
    assert isinstance(body["detail"], str)
    assert body["request_id"]


def test_register_invite_inactive(client):
    """邀请码被停用 → invite.inactive"""
    _make_invite(is_active=False)
    resp = _register(client)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invite.inactive"


def test_register_invite_expired(client):
    """邀请码过期 → invite.expired"""
    _make_invite(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    resp = _register(client)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invite.expired"


def test_register_invite_exhausted(client):
    """邀请码名额用完 → invite.exhausted"""
    _make_invite(max_uses=1, used_count=1)
    resp = _register(client)
    assert resp.status_code == 400
    assert resp.json()["code"] == "invite.exhausted"


def test_register_duplicate_username(client):
    """用户名重复 → resource.conflict（不是 400 校验失败）"""
    _make_user("test1")
    _make_invite()
    resp = _register(client, username="test1")
    assert resp.status_code == 409
    assert resp.json()["code"] == "resource.conflict"


def test_register_weak_password(client):
    """弱密码 → request.validation_failed"""
    _make_invite()
    resp = _register(client, password="abc")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "request.validation_failed"
    assert "不合规" in body["detail"]


def test_register_invalid_invite_does_not_create_user(client):
    """邀请码不对 → 不能建出用户（名额也不能被占）"""
    invite_id = _make_invite()
    resp = _register(client, invite_code="TQB-WRONG-CODE-1")
    assert resp.status_code == 400

    with Session(engine) as session:
        from sqlmodel import select

        assert session.exec(select(User).where(User.username == "newteacher")).first() is None
        invite = session.get(Invite, invite_id)
        assert invite.used_count == 0, "注册失败不能占名额"


def test_register_code_is_case_insensitive(client):
    """老师从微信复制来的码可能大小写混着 —— 照样能用"""
    _make_invite(code="TQB-ABCD-EFGH-IJKL")
    resp = _register(client, invite_code="  tqb-abcd-efgh-ijkl  ")
    assert resp.status_code == 200


def test_register_twice_with_single_use_invite(client):
    """一次性的码：第一个人用掉，第二个人就注册不了"""
    _make_invite(max_uses=1)
    assert _register(client, username="teacher1").status_code == 200
    resp = _register(client, username="teacher2")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invite.exhausted"


# ============================================================
# 邀请码管理接口（仅管理员）
# ============================================================

def test_admin_invites_require_login(client):
    resp = client.get("/api/auth/invites")
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.required"


def test_non_admin_cannot_manage_invites(client):
    """普通用户调管理接口 → 403 auth.forbidden"""
    _make_user("test1")           # 普通用户
    token = _login(client).json()["token"]
    h = _h(token)

    assert client.get("/api/auth/invites", headers=h).status_code == 403
    assert client.post(
        "/api/auth/invites", headers=h, json={"label": "x", "max_uses": 1}
    ).status_code == 403
    assert client.patch(
        "/api/auth/invites/1", headers=h, json={"is_active": False}
    ).status_code == 403

    body = client.get("/api/auth/invites", headers=h).json()
    assert body["code"] == "auth.forbidden"


def test_admin_can_create_list_and_disable_invites(client):
    """管理员：生成 → 列表能看到 → 停用"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss").json()["token"]
    h = _h(token)

    resp = client.post(
        "/api/auth/invites",
        headers=h,
        json={"label": "高一组", "max_uses": 3, "expires_days": 7},
    )
    assert resp.status_code == 200
    created = resp.json()
    assert created["code"].startswith("TQB-")
    assert created["max_uses"] == 3
    assert created["remaining"] == 3
    assert created["state"] == "active"
    assert created["expires_at"]

    listing = client.get("/api/auth/invites", headers=h).json()
    assert listing["total"] == 1
    assert listing["items"][0]["code"] == created["code"]

    # 停用
    resp = client.patch(
        f"/api/auth/invites/{created['id']}",
        headers=h,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["state"] == "disabled"

    # 停用后拿这个码注册 → invite.inactive
    reg = _register(client, invite_code=created["code"])
    assert reg.status_code == 400
    assert reg.json()["code"] == "invite.inactive"


def test_admin_can_change_max_uses(client):
    _make_user("boss", is_admin=True)
    token = _login(client, "boss").json()["token"]
    h = _h(token)

    invite_id = _make_invite(max_uses=1, used_count=1)
    resp = client.patch(
        f"/api/auth/invites/{invite_id}",
        headers=h,
        json={"max_uses": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["max_uses"] == 5
    assert resp.json()["remaining"] == 4
    assert resp.json()["state"] == "active"


def test_admin_patch_missing_invite_404(client):
    _make_user("boss", is_admin=True)
    token = _login(client, "boss").json()["token"]
    resp = client.patch(
        "/api/auth/invites/999999",
        headers=_h(token),
        json={"is_active": False},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "resource.not_found"


def test_me_returns_is_admin(client):
    """/me 要带 is_admin —— 前端据此显示管理员入口"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss").json()["token"]
    body = client.get("/api/auth/me", headers=_h(token)).json()
    assert body["is_admin"] is True

    _make_user("plain")
    token2 = _login(client, "plain").json()["token"]
    body2 = client.get("/api/auth/me", headers=_h(token2)).json()
    assert body2["is_admin"] is False


# ============================================================
# 脚本
# ============================================================

def test_generate_invites_script(tmp_path, monkeypatch):
    """批量生成脚本能跑，产出 N 个不重复的码"""
    from app.scripts import generate_invites

    with Session(engine) as session:
        from sqlmodel import select

        before = len(session.exec(select(Invite)).all())

    monkeypatch.setattr(sys, "argv", [
        "generate_invites", "--count", "3", "--label", "批量测试",
        "--max-uses", "2", "--expires-days", "7",
    ])
    assert generate_invites.main() == 0

    with Session(engine) as session:
        from sqlmodel import select

        invites = session.exec(select(Invite)).all()
        assert len(invites) == before + 3
        codes = [i.code for i in invites]
        assert len(set(codes)) == 3, "码不能重复"
        for inv in invites:
            assert inv.max_uses == 2
            assert inv.label == "批量测试"
            assert inv.expires_at is not None
