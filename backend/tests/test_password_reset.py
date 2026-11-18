"""
手机号 + 验证码重置密码 —— 端到端测试（lesson-40）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_password_reset.py -v

为什么全程 mock 阿里云
---------------------
真发短信要花钱（0.06 元/条）还要真手机号。所以把 services/sms.py 里的
_client() 换成假客户端：发码假装成功、核验假装 PASS / UNKNOWN。

被测的真逻辑是**我们自己的**那些：
- 用途隔离：注册用的码不许拿去改密码（阿里云那边不认用途，隔离只能在我们这边做）
- reset 用途的码只对**已注册**的号发
- 改密前查号 → 验密码强度 → 核验 → 改密码 → 踢掉**所有**旧会话 → 签发新会话
- 共享试用账号不给自助改密
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import SmsAttempt, User  # noqa: E402
from app.services import sms  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Test1234"
NEW_PASSWORD = "NewTest5678"
PHONE = "13800138000"


# === 假阿里云客户端 ===


class _FakeBody:
    def __init__(self, success=True, verify_result="PASS"):
        self.success = success
        self.model = type("M", (), {"verify_result": verify_result})()


class _FakeResponse:
    def __init__(self, body):
        self.body = body


class _FakeClient:
    """假装是阿里云客户端。"""

    def __init__(self, send_success=True, verify_result="PASS"):
        self.send_success = send_success
        self.verify_result = verify_result
        self.sent = None
        self.checked = None

    def send_sms_verify_code(self, request):
        self.sent = request
        return _FakeResponse(_FakeBody(self.send_success))

    def check_sms_verify_code(self, request):
        self.checked = request
        return _FakeResponse(_FakeBody(True, self.verify_result))


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清库（顺序按外键依赖）。"""
    with Session(engine) as session:
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM uploads",
            "DELETE FROM paper_questions",
            "DELETE FROM papers",
            "DELETE FROM question_tags",
            "DELETE FROM tags",
            "DELETE FROM questions",
            "DELETE FROM categories",
            "DELETE FROM sms_attempts",
            "DELETE FROM users",
        ):
            session.exec(text(sql))
        session.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_sms(monkeypatch):
    """装上假客户端 + 假装环境变量配好了。"""
    fake = _FakeClient()
    monkeypatch.setattr(sms, "_client", lambda: fake)
    for name, value in (
        (sms.ENV_AK, "test-ak"),
        (sms.ENV_SECRET, "test-sk"),
        (sms.ENV_SIGN, "测试签名"),
        (sms.ENV_TEMPLATE_CODE, "100001"),
    ):
        monkeypatch.setenv(name, value)
    return fake


def _make_user(username: str, *, phone: str | None = None, password: str = PASSWORD,
               allow_password_change: bool = True, must_change_password: bool = False) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            phone=phone,
            display_name="测试",
            password_hash=hash_password(password),
            must_change_password=must_change_password,
            allow_password_change=allow_password_change,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _last_send_purpose(phone: str):
    with Session(engine) as session:
        row = session.exec(
            select(SmsAttempt)
            .where(SmsAttempt.phone == phone, SmsAttempt.action == "send")
            .order_by(SmsAttempt.created_at.desc())
        ).first()
        return row.purpose if row else None


# === 发码（用途） ===


def test_reset_send_requires_registered_phone(client, fake_sms):
    """没注册的号不该收到改密验证码 —— 那它想的是注册。"""
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "auth.account_not_found"
    assert fake_sms.sent is None      # 一条都没发出去


def test_reset_send_records_purpose(client, fake_sms):
    """已注册的号发 reset 码 —— 流水里要记下用途。"""
    _make_user(PHONE, phone=PHONE)
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})
    assert resp.status_code == 200
    assert resp.json()["sent"] is True
    assert _last_send_purpose(PHONE) == "reset"


def test_register_send_defaults_to_register_purpose(client, fake_sms):
    """不传 purpose = 注册（老前端不受影响）。"""
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 200
    assert _last_send_purpose(PHONE) == "register"


def test_sms_send_rejects_unknown_purpose(client, fake_sms):
    """用途乱传要拒掉，不能变成什么都能干的码。"""
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "whatever"})
    assert resp.status_code == 400
    assert fake_sms.sent is None


# === 用途隔离 ===


def test_register_code_cannot_be_used_to_reset(client, fake_sms):
    """注册用的码不能拿去改密码 —— 阿里云不认用途，这层隔离只能我们自己做。"""
    _make_user(PHONE, phone=PHONE)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "register"})

    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "sms.code_invalid"
    assert "注册" in resp.json()["detail"]


# === 重置密码 ===


def test_reset_unregistered_phone(client, fake_sms):
    """没注册的号没有密码可以重置。"""
    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "auth.account_not_found"


def test_reset_rejects_weak_password(client, fake_sms):
    """弱密码要在核验验证码**之前**就拒 —— 别白烧一次核验机会。"""
    _make_user(PHONE, phone=PHONE)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})

    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"

    # 密码没被动过
    login = client.post("/api/auth/login", json={"account": PHONE, "password": PASSWORD})
    assert login.status_code == 200


def test_reset_wrong_code(client, fake_sms):
    """验证码不对 → 400，密码不变。"""
    _make_user(PHONE, phone=PHONE)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})
    fake_sms.verify_result = "UNKNOWN"

    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "sms.code_invalid"

    login = client.post("/api/auth/login", json={"account": PHONE, "password": PASSWORD})
    assert login.status_code == 200


def test_reset_success_changes_password_and_logs_in(client, fake_sms):
    """成功路径：改密码 → 签发新会话 → 直接能登。"""
    _make_user(PHONE, phone=PHONE)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})

    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    # UserOut 里没有 phone 字段（登录响应只给 username/display_name 等）
    assert body["user"]["username"] == PHONE

    # 新密码能登
    assert client.post(
        "/api/auth/login", json={"account": PHONE, "password": NEW_PASSWORD}
    ).status_code == 200
    # 旧密码不能登
    assert client.post(
        "/api/auth/login", json={"account": PHONE, "password": PASSWORD}
    ).status_code == 401


def test_reset_revokes_all_old_sessions(client, fake_sms):
    """改完密码，旧会话全失效 —— 忘密码的场景下不能留后门。"""
    _make_user(PHONE, phone=PHONE)
    old_token = client.post(
        "/api/auth/login", json={"account": PHONE, "password": PASSWORD}
    ).json()["token"]
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 200

    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})
    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200

    # 旧 token 失效
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401


def test_reset_clears_must_change_password(client, fake_sms):
    """重置完不该再要求改密码（老师自己设的）。"""
    _make_user(PHONE, phone=PHONE, must_change_password=True)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})

    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["must_change_password"] is False


def test_reset_shared_account_forbidden(client, fake_sms):
    """共享试用账号不给自助改密 —— 改一个所有人掉线。"""
    _make_user(PHONE, phone=PHONE, allow_password_change=False)
    resp = client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.password_change_locked"


def test_reset_does_not_store_plaintext_code(client, fake_sms):
    """库里不能出现验证码明文（老规矩，重置路径也得守）。"""
    _make_user(PHONE, phone=PHONE)
    client.post("/api/auth/sms/send", json={"phone": PHONE, "purpose": "reset"})
    client.post(
        "/api/auth/password/reset",
        json={"phone": PHONE, "code": "123456", "new_password": NEW_PASSWORD},
    )

    with Session(engine) as session:
        rows = session.exec(select(SmsAttempt)).all()
        for row in rows:
            assert "123456" not in repr(row.__dict__)
