"""用户体系端到端测试 — lesson-11

覆盖：
- 建号 + 密码强度校验
- 登录（正确/错误密码/不存在用户）
- 会话签发与校验
- 改密（+ 踢掉其他设备）
- 数据隔离（test1 看不到 test2 的题）
- 注销后 token 失效
- 停用账号立刻踢下线

跑法：
    cd lesson-02
    venv/bin/python -m pytest tests/test_auth.py -v
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import check_password_strength, hash_password, verify_password  # noqa: E402
from app.services.auth import create_session, get_session_by_token  # noqa: E402

PASSWORD = "Test1234"
OTHER_PASSWORD = "Other1234"


# === fixtures ===


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清干净用户相关数据"""
    with Session(engine) as session:
        # ⚠️ 删除顺序要紧：先删引用方，再删被引用方（外键约束）
        #    顺序错了会报 ForeignKeyViolation
        for model in (Session_, Upload, PaperQuestion, Paper, Question, User):
            session.exec(delete(model))
        session.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _make_user(username: str, display_name: str = "测试", password: str = PASSWORD) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _make_question(user_id: int, content: str = "测试题目") -> int:
    with Session(engine) as session:
        q = Question(user_id=user_id, content_plain=content, content_markdown=content)
        session.add(q)
        session.commit()
        session.refresh(q)
        return q.id or 0


def _login(client, username: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# === 密码强度 ===


def test_password_strength_rules():
    assert check_password_strength("Abc12345") == []
    assert check_password_strength("abc123")          # 太短 + 无大写
    assert check_password_strength("abcdefgh")        # 无大写无数字
    assert check_password_strength("ABCDEFGH")        # 无小写无数字
    assert check_password_strength("Abcdefgh")        # 无数字
    assert check_password_strength("Abc12345") == []


def test_hash_and_verify():
    h = hash_password(PASSWORD)
    assert h != PASSWORD                      # 绝不含明文
    assert h.startswith("$2b$")                # bcrypt
    assert verify_password(PASSWORD, h)
    assert not verify_password("Wrong1234", h)
    assert hash_password(PASSWORD) != h        # 两次哈希不同（自带 salt）


# === 登录 ===


def test_login_success(client):
    _make_user("test1")
    resp = _login(client, "test1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"]
    assert data["user"]["username"] == "test1"


def test_login_wrong_password(client):
    _make_user("test1")
    resp = _login(client, "test1", "Wrong1234")
    assert resp.status_code == 401
    assert "用户名或密码错误" in resp.json()["detail"]


def test_login_unknown_user(client):
    resp = _login(client, "nobody")
    assert resp.status_code == 401
    # 文案要跟密码错一样 —— 不泄露用户是否存在
    assert "用户名或密码错误" in resp.json()["detail"]


def test_login_inactive_user(client):
    uid = _make_user("test1")
    with Session(engine) as session:
        user = session.get(User, uid)
        user.is_active = False
        session.add(user)
        session.commit()
    resp = _login(client, "test1")
    assert resp.status_code == 403


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_with_token(client):
    _make_user("test1")
    token = _login(client, "test1").json()["token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "test1"


def test_logout_invalidates_token(client):
    _make_user("test1")
    token = _login(client, "test1").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


# === 改密 ===


def test_change_password(client):
    _make_user("test1")
    token = _login(client, "test1").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": PASSWORD, "new_password": OTHER_PASSWORD},
    )
    assert resp.status_code == 200
    # 改完旧密码不能用了
    assert _login(client, "test1", PASSWORD).status_code == 401
    assert _login(client, "test1", OTHER_PASSWORD).status_code == 200


def test_change_password_wrong_old(client):
    _make_user("test1")
    token = _login(client, "test1").json()["token"]
    resp = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "Wrong1234", "new_password": OTHER_PASSWORD},
    )
    assert resp.status_code == 401


def test_change_password_weak_new(client):
    _make_user("test1")
    token = _login(client, "test1").json()["token"]
    resp = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": PASSWORD, "new_password": "abc"},
    )
    assert resp.status_code == 400
    assert "不合规" in resp.json()["detail"]


def test_change_password_revokes_other_sessions(client):
    _make_user("test1")
    token_a = _login(client, "test1").json()["token"]
    token_b = _login(client, "test1").json()["token"]

    resp = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"old_password": PASSWORD, "new_password": OTHER_PASSWORD},
    )
    assert resp.status_code == 200
    # 改密后所有会话都被踢（含当前这个 —— 改完要重新登录）
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"}).status_code == 401


# === 数据隔离 ===


def test_questions_isolated_between_users(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    q1 = _make_question(uid1, "test1 的题")
    _make_question(uid2, "test2 的题")

    token1 = _login(client, "test1").json()["token"]
    token2 = _login(client, "test2").json()["token"]
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    r1 = client.get("/api/questions/", headers=h1).json()
    r2 = client.get("/api/questions/", headers=h2).json()

    assert r1["total"] == 1
    assert r2["total"] == 1
    assert "test1 的题" in r1["items"][0]["content_plain"]
    assert "test2 的题" in r2["items"][0]["content_plain"]
    # 互相看不到
    assert "test2 的题" not in r1["items"][0]["content_plain"]
    assert client.get(f"/api/questions/{q1}", headers=h2).status_code == 404


def test_create_question_requires_login(client):
    resp = client.post("/api/questions/", json={"content_plain": "x"})
    assert resp.status_code == 401


def test_create_question_records_owner(client):
    uid = _make_user("test1")
    token = _login(client, "test1").json()["token"]
    resp = client.post(
        "/api/questions/",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_plain": "新题", "content_markdown": "新题"},
    )
    assert resp.status_code == 200
    with Session(engine) as session:
        q = session.exec(select(Question)).first()
        assert q.user_id == uid


def test_papers_isolated(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    with Session(engine) as session:
        p2 = Paper(user_id=uid2, title="test2 的卷")
        session.add(p2)
        session.commit()
        pid2 = p2.id or 0

    token2 = _login(client, "test2").json()["token"]
    h2 = {"Authorization": f"Bearer {token2}"}
    assert client.get(f"/api/papers/{pid2}", headers=h2).status_code == 200

    token1 = _login(client, "test1").json()["token"]
    h1 = {"Authorization": f"Bearer {token1}"}
    # test1 看不到 test2 的卷 —— 404 而不是 403
    assert client.get(f"/api/papers/{pid2}", headers=h1).status_code == 404
    assert client.get(f"/api/papers/{pid2}/export.pdf", headers=h1).status_code == 404
    assert client.get("/api/papers/", headers=h1).json()["total"] == 0


def test_stopped_user_is_kicked_out(client):
    uid = _make_user("test1")
    token = _login(client, "test1").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200

    # 停用账号
    with Session(engine) as session:
        user = session.get(User, uid)
        user.is_active = False
        session.add(user)
        session.commit()

    # 立刻失效（可踢下线是选服务端 Session 的理由）
    resp = client.get("/api/auth/me", headers=h)
    assert resp.status_code == 403


def test_session_token_hashed_in_db():
    """库里存的是哈希不是明文 token"""
    uid = _make_user("test1")
    with Session(engine) as session:
        token, record = create_session(session.get(User, uid), session)
        assert token not in record.token_hash
        assert len(record.token_hash) == 64
        # 能用明文 token 找到会话
        assert get_session_by_token(token, session) is not None
        assert get_session_by_token("wrong", session) is None
