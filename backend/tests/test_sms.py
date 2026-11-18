"""
短信注册 + 手机号登录 端到端测试 — lesson-39

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_sms.py -v

为什么全程 mock 阿里云
---------------------
真发短信要花钱（0.06 元/条）还要真手机号，测试里不能干这个。
所以把 ``services/sms.py`` 里的 ``_client()`` 换成一个假客户端：
- 发码：假装成功（body.success = True）
- 核验：假装 PASS 或 UNKNOWN

被测的真逻辑是**我们自己的**那些：
- 频控（同号 60 秒、同号每天 10 条、同 IP 每小时 20 条）
- 核验失败次数上限（防穷举 6 位码）
- 注册流程的顺序（查重 → 密码强度 → 核验 → 建号 → 签发会话）
- 登录时手机号 / 旧用户名两条路都能找到人
- **库里不存验证码明文**
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Invite, SmsAttempt, User  # noqa: E402
from app.services import sms  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Test1234"
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
    """假装是阿里云客户端。

    记录收到的请求 —— 测试要断言我们传对了参数
    （比如 template_param 里必须是 ##code##，否则阿里云核不了）。
    """

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
    """每个测试前清库（顺序按外键依赖）"""
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
def ip_client():
    """带固定来源 IP 的客户端。

    为什么单独一个：测「同 IP 每小时上限」得知道请求是从哪个 IP 来的，
    而 TestClient 默认来源是 testclient（不是真 IP）。
    """
    return TestClient(app, client=("1.2.3.4", 50000))


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


def _make_user(username: str, *, phone: str | None = None, password: str = PASSWORD) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            phone=phone,
            display_name="测试",
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _seed_attempt(phone: str, *, action="send", ok=True, minutes_ago=10, ip=""):
    """塞一条历史流水（用来把频控窗口填满）。"""
    with Session(engine) as session:
        session.add(
            SmsAttempt(
                phone=phone,
                ip=ip,
                action=action,
                ok=ok,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
            )
        )
        session.commit()


# === 未配置 ===


def test_sms_not_configured_returns_503(client, monkeypatch):
    """没配 AK 时发码要明确说「找管理员」，不能 500。"""
    for name in (sms.ENV_AK, sms.ENV_SECRET, sms.ENV_SIGN, sms.ENV_TEMPLATE_CODE):
        monkeypatch.delenv(name, raising=False)

    resp = client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "sms.not_configured"
    assert "管理员" in body["detail"]


# === 发码 ===


def test_send_code_success(client, fake_sms):
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] is True
    assert body["cooldown"] == 60

    # 参数必须是阿里云能核验的形态
    assert fake_sms.sent is not None
    assert "##code##" in fake_sms.sent.template_param
    assert fake_sms.sent.phone_number == PHONE
    assert fake_sms.sent.code_length == 6

    # 流水落库（频控 + 审计要用）
    with Session(engine) as session:
        rows = session.exec(select(SmsAttempt)).all()
    assert len(rows) == 1
    assert rows[0].phone == PHONE
    assert rows[0].action == "send"
    assert rows[0].ok is True


def test_send_code_rejects_bad_phone(client, fake_sms):
    resp = client.post("/api/auth/sms/send", json={"phone": "12345"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"


def test_send_code_resend_limited_60s(client, fake_sms):
    """同号 60 秒内只能发一条。"""
    assert client.post("/api/auth/sms/send", json={"phone": PHONE}).status_code == 200
    resp = client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 429
    assert resp.json()["code"] == "sms.rate_limited"


def test_send_code_daily_limit(client, fake_sms):
    """同号每天 10 条上限。"""
    for _ in range(sms.PHONE_DAILY_LIMIT):
        _seed_attempt(PHONE, action="send", ok=True, minutes_ago=10)

    resp = client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 429
    assert resp.json()["code"] == "sms.rate_limited"


def test_send_code_ip_hourly_limit(ip_client, fake_sms):
    """同 IP 每小时 20 条上限（防一个人换号狂发）。"""
    for i in range(sms.IP_HOURLY_LIMIT):
        _seed_attempt(
            f"1380013{i:04d}",
            action="send",
            ok=True,
            minutes_ago=5,
            ip="1.2.3.4",
        )

    resp = ip_client.post("/api/auth/sms/send", json={"phone": PHONE})
    assert resp.status_code == 429
    assert resp.json()["code"] == "sms.rate_limited"


# === 注册 ===


def test_register_with_phone_and_code(client, fake_sms):
    """手机号 + 验证码注册 → 直接签发会话。"""
    resp = client.post(
        "/api/auth/register",
        json={
            "phone": PHONE,
            "code": "123456",
            "password": PASSWORD,
            "display_name": "张老师",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["user"]["username"] == PHONE
    assert body["user"]["display_name"] == "张老师"

    # 核验请求带对了手机号和验证码
    assert fake_sms.checked.phone_number == PHONE
    assert fake_sms.checked.verify_code == "123456"

    # 用户落库，phone 与 username 都填了
    with Session(engine) as session:
        user = session.exec(select(User)).first()
    assert user.phone == PHONE


def test_register_wrong_code(client, fake_sms):
    fake_sms.verify_result = "UNKNOWN"
    resp = client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "000000", "password": PASSWORD},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "sms.code_invalid"


def test_register_phone_already_taken(client, fake_sms):
    """同一个号不能注册两次。"""
    _make_user("13800138000", phone=PHONE)
    resp = client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "123456", "password": PASSWORD},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "auth.phone_taken"


def test_register_weak_password_rejected_before_sms(client, fake_sms):
    """弱密码要在调阿里云**之前**就挡掉（不浪费一次核验调用）。"""
    resp = client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "123456", "password": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"
    assert fake_sms.checked is None


def test_verify_fail_limit(client, fake_sms):
    """同号每小时核验失败 10 次就锁（防穷举 6 位码）。"""
    for _ in range(sms.VERIFY_FAIL_HOURLY_LIMIT):
        _seed_attempt(PHONE, action="verify", ok=False, minutes_ago=3)

    fake_sms.verify_result = "UNKNOWN"
    resp = client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "000000", "password": PASSWORD},
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == "sms.rate_limited"


def test_no_plaintext_code_in_db(client, fake_sms):
    """库里不能有验证码明文 —— 拖库也换不来一个号。"""
    client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "123456", "password": PASSWORD},
    )
    with Session(engine) as session:
        columns = {c.name for c in SmsAttempt.__table__.columns}
    assert "code" not in columns
    assert "verify_code" not in columns


# === 邀请码退役 ===


def test_stopped_invite_no_longer_blocks_registration(client, fake_sms):
    """邀请码已退役：码停用了照样能注册（短信注册取代了它）。

    ⚠️ 这条是**契约声明**，不是漏洞 —— 老大 2026-11-18 拍板
    「直接短信注册替代现有邀请码注册」。
    """
    with Session(engine) as session:
        session.add(
            Invite(
                code="TQB-STOPPED-0001",
                label="已停用",
                max_uses=1,
                used_count=0,
                is_active=False,
            )
        )
        session.commit()

    resp = client.post(
        "/api/auth/register",
        json={"phone": PHONE, "code": "123456", "password": PASSWORD},
    )
    assert resp.status_code == 200

    # 邀请码名额也不再被占用（注册流程压根不碰它）
    with Session(engine) as session:
        invite = session.exec(select(Invite)).first()
    assert invite.used_count == 0

# === 登录 ===


def test_login_with_phone(client, fake_sms):
    """手机号就是账号。"""
    _make_user(PHONE, phone=PHONE)
    resp = client.post("/api/auth/login", json={"account": PHONE, "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == PHONE


def test_login_with_legacy_username(client, fake_sms):
    """存量账号（只有 username 没有 phone）还能用原用户名登录。"""
    _make_user("test1")
    resp = client.post("/api/auth/login", json={"account": "test1", "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "test1"


def test_login_old_field_username_still_works(client, fake_sms):
    """旧前端传 username 字段也要能登（别把存量页面打挂）。"""
    _make_user("test1")
    resp = client.post("/api/auth/login", json={"username": "test1", "password": PASSWORD})
    assert resp.status_code == 200


def test_login_account_not_found(client, fake_sms):
    """账号不存在 → 404 + auth.account_not_found（前端据此引导去注册）。"""
    resp = client.post("/api/auth/login", json={"account": PHONE, "password": PASSWORD})
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "auth.account_not_found"
    assert "注册" in body["detail"]


def test_login_wrong_password(client, fake_sms):
    """密码错 → 401 + auth.invalid_credentials（跟「号不存在」分开）。"""
    _make_user(PHONE, phone=PHONE)
    resp = client.post("/api/auth/login", json={"account": PHONE, "password": "Wrong1234"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.invalid_credentials"


def test_login_disabled_account(client, fake_sms):
    _make_user(PHONE, phone=PHONE)
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        user.is_active = False
        session.add(user)
        session.commit()

    resp = client.post("/api/auth/login", json={"account": PHONE, "password": PASSWORD})
    assert resp.status_code == 403
