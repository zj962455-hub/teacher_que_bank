"""邀请码管理测试 — 课 34 的邀请码 + lesson-39 的退役说明

⚠️ lesson-39 起，**注册入口已改成手机号 + 短信验证码**（见 tests/test_sms.py），
邀请码不再参与注册流程。这份文件现在只保留两件事的覆盖：
- 邀请码管理接口（仅管理员）仍然正常工作
- 旧注册契约确实被废弃了（老 payload 不该再被接受）

覆盖：
- 注册成功并自动登录（直接拿到 token，/me 能用）
- 邀请码四种失败：不存在 / 已停用 / 已过期 / 已用尽（各自机器码）
- 用户名重复 → resource.conflict
- 弱密码 → request.validation_failed
- 邀请码名额用一次加一次
- 管理接口：只有管理员能调（普通用户 403、未登录 401）
- 管理接口：生成 / 列表 / 停用 / 改名额

跑法：
    cd backend
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



# ============================================================
# 注册入口（lesson-39：短信注册已替代邀请码注册）
# ============================================================


def test_register_endpoint_now_requires_phone_and_code(client):
    """旧的「用户名 + 邀请码」注册契约已经废弃。

    现在注册要手机号 + 短信验证码（完整流程见 tests/test_sms.py）。
    这条测试钉住契约：旧 payload 不该再被接受 ——
    否则前端某个老页面还在走老路时不会报错，只会注册出奇怪的账号。
    """
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "newteacher",
            "password": STRONG_PASSWORD,
            "invite_code": "TQB-TEST-CODE-0001",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    # 统一错误契约：detail 永远是字符串（前端直接显示）
    assert isinstance(body["detail"], str)
    assert body["code"] == "request.validation_failed"

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

    # ⚠️ 邀请码不再参与注册（lesson-39 起由短信验证码接管），
    #    所以这里只验「停用状态生效」，不再验「拿码注册会被拦」。


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
