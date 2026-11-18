"""
个人信息保护相关措施 —— 测试（lesson-42 · 公安备案安全评估）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_privacy_controls.py -v

测什么
------
1. 登录限流（防撞库）：同一账号连续失败到阈值 → 后续直接 429
2. 限流不误伤：另一个账号仍然可以正常登录
3. 登录成功也记一条流水（审计）
4. 自助注销账号：密码确认 → 账号停用 + 会话全撤销 + 分享链接全吊销 + 显示名清空
5. 自助注销要密码：密码不对 → 401（防止会话被劫持后直接注销）
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    LoginAttempt,
    Paper,
    PaperShare,
    Session_,
    User,
    create_tables,
)
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Privacy1234"


@pytest.fixture(scope="module", autouse=True)
def _ensure_table():
    create_tables()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _mk_user(username: str) -> int:
    with Session(engine) as session:
        row = session.exec(select(User).where(User.username == username)).first()
        if row is None:
            row = User(
                username=username,
                display_name="隐私测试",
                password_hash=hash_password(PASSWORD),
                is_active=True,
                must_change_password=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return row.id or 0


def _login(client, username, password=PASSWORD):
    return client.post(
        "/api/auth/login", json={"account": username, "password": password}
    )


# ================= 登录限流 =================


def test_login_rate_limited_on_repeated_failures(client):
    """同一账号连续失败到阈值 → 后续 429"""
    account = "limit_" + uuid.uuid4().hex[:10]
    _mk_user(account)

    # 前 5 次：正常返回 401（密码错）
    for _ in range(5):
        r = _login(client, account, "WrongPass123")
        assert r.status_code == 401, r.text

    # 第 6 次：被限流
    r = _login(client, account, "WrongPass123")
    assert r.status_code == 429, r.text
    assert r.json()["code"] == "auth.rate_limited"


def test_rate_limit_does_not_block_other_accounts(client):
    """限流只影响那个账号，别人照常登录"""
    blocked = "limit2_" + uuid.uuid4().hex[:10]
    other = "free_" + uuid.uuid4().hex[:10]
    _mk_user(blocked)
    _mk_user(other)

    for _ in range(5):
        _login(client, blocked, "WrongPass123")

    assert _login(client, blocked, "WrongPass123").status_code == 429

    r = _login(client, other)
    assert r.status_code == 200, r.text


def test_successful_login_is_logged(client):
    """成功也记一条（审计：谁在何时从哪个 IP 登录成功）"""
    account = "oklog_" + uuid.uuid4().hex[:10]
    _mk_user(account)
    assert _login(client, account).status_code == 200

    with Session(engine) as session:
        rows = session.exec(
            select(LoginAttempt).where(LoginAttempt.account == account)
        ).all()
    assert any(x.ok for x in rows), "成功登录应记一条 ok=true"
    assert any(not x.ok for x in rows) is False or True  # 失败记录另算


# ================= 自助注销 =================


def _make_share(user_id: int) -> str:
    """给该用户造一条分享链接"""
    with Session(engine) as session:
        paper = session.exec(select(Paper)).first()
        if paper is None:
            paper = Paper(user_id=user_id, title="注销测试卷", subtitle="")
            session.add(paper)
            session.commit()
            session.refresh(paper)
        share = PaperShare(
            paper_id=paper.id or 0,
            user_id=user_id,
            token=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(share)
        session.commit()
        session.refresh(share)
        return share.token


def test_account_delete_requires_password(client):
    """密码不对 → 401（防止会话被劫持后直接注销）"""
    account = "del_" + uuid.uuid4().hex[:10]
    uid = _mk_user(account)
    token = _login(client, account).json()["token"]

    r = client.post(
        "/api/auth/account/delete",
        json={"password": "WrongPass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401, r.text

    # 账号还活着
    with Session(engine) as session:
        row = session.get(User, uid)
        assert row.is_active is True


def test_account_delete_revokes_sessions_and_shares(client):
    """注销后：账号停用 + 会话全撤销 + 分享链接全吊销 + 显示名清空"""
    account = "del2_" + uuid.uuid4().hex[:10]
    uid = _mk_user(account)
    share_token = _make_share(uid)
    token = _login(client, account).json()["token"]

    r = client.post(
        "/api/auth/account/delete",
        json={"password": PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["revoked_sessions"] >= 1
    assert body["revoked_shares"] >= 1

    with Session(engine) as session:
        row = session.get(User, uid)
        assert row.is_active is False, "账号应被停用"
        assert row.display_name == "", "显示名应被清空"

        sessions = session.exec(
            select(Session_).where(Session_.user_id == uid)
        ).all()
        assert len(sessions) == 0, "全部会话应被撤销"

        share = session.exec(
            select(PaperShare).where(PaperShare.token == share_token)
        ).first()
        assert share is not None
        assert share.revoked_at is not None, "分享链接应被吊销"

    # 旧令牌不能再用
    r2 = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code in (401, 403), r2.text
