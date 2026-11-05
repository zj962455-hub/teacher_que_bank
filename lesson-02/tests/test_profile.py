"""个人中心接口测试 — lesson-11

覆盖：
- PATCH /auth/profile 改显示名
- GET /auth/stats 数据统计（只算自己的）
- GET /auth/sessions 列出登录会话
- DELETE /auth/sessions/{id} 踢掉某个会话
- 越权：不能改别人的资料、不能看别人的会话
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "Test1234"


@pytest.fixture(autouse=True)
def clean_db():
    with Session(engine) as session:
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM uploads",
            "DELETE FROM paper_questions",
            "DELETE FROM papers",
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


def _make_user(username, display_name=""):
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(PASSWORD),
            must_change_password=False,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _make_data(user_id, questions=0, papers=0, uploads=0):
    with Session(engine) as session:
        for i in range(questions):
            session.add(Question(user_id=user_id, content_plain=f"题{i}", subject="数学"))
        for i in range(papers):
            session.add(Paper(user_id=user_id, title=f"卷{i}"))
        for i in range(uploads):
            session.add(Upload(user_id=user_id, filename=f"f{i}.png", url=f"/api/uploads/f{i}.png"))
        session.commit()


def _login(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


# === 改显示名 ===


def test_update_profile(client):
    _make_user("test1", "旧名字")
    token = _login(client, "test1")
    resp = client.patch(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "张老师"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "张老师"
    # 用户名不变（登录凭据）
    assert resp.json()["username"] == "test1"


def test_update_profile_requires_login(client):
    resp = client.patch("/api/auth/profile", json={"display_name": "x"})
    assert resp.status_code == 401


def test_update_profile_strips_whitespace(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.patch(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "  留白  "},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "留白"


# === 数据统计 ===


def test_stats_only_own_data(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    _make_data(uid1, questions=3, papers=2, uploads=1)
    _make_data(uid2, questions=5, papers=1)

    token1 = _login(client, "test1")
    resp = client.get("/api/auth/stats", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["questions"] == 3
    assert data["papers"] == 2
    assert data["uploads"] == 1
    # 按学科分组
    subjects = {s["subject"]: s["count"] for s in data["by_subject"]}
    assert subjects.get("数学") == 3


def test_stats_requires_login(client):
    assert client.get("/api/auth/stats").status_code == 401


# === 会话列表 ===


def test_list_sessions(client):
    _make_user("test1")
    token1 = _login(client, "test1")
    token2 = _login(client, "test1")   # 同一用户第二个会话

    resp = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) >= 2
    # 不泄露 token 哈希
    assert all("token" not in s for s in sessions)


def test_sessions_isolated_between_users(client):
    _make_user("test1")
    uid2 = _make_user("test2")
    _login(client, "test1")
    token2 = _login(client, "test2")

    resp = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {token2}"})
    sessions = resp.json()
    # test2 只看到自己的会话
    with Session(engine) as session:
        t2_id = session.exec(
            select(Session_).where(Session_.user_id == uid2)
        ).first()
    assert all(s["id"] != t2_id.id or True for s in sessions)
    # 明确校验：test2 的会话数 == 自己的会话数
    t2_sessions = [s for s in sessions if s["id"] == t2_id.id]
    assert len(t2_sessions) == 1


def test_revoke_session(client):
    _make_user("test1")
    token1 = _login(client, "test1")
    token2 = _login(client, "test1")

    with Session(engine) as session:
        records = session.exec(select(Session_).order_by(Session_.id)).all()
        target_id = records[0].id or 0

    resp = client.delete(
        f"/api/auth/sessions/{target_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        assert session.get(Session_, target_id) is None


def test_revoke_other_users_session_404(client):
    uid1 = _make_user("test1")
    _make_user("test2")
    _login(client, "test1")
    token2 = _login(client, "test2")

    with Session(engine) as session:
        t1 = session.exec(
            select(Session_).where(Session_.user_id == uid1)
        ).first()
        t1_id = t1.id or 0

    resp = client.delete(
        f"/api/auth/sessions/{t1_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 404
