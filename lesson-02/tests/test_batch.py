"""批量操作 / 最近编辑 测试 — lesson-11

覆盖：
- POST /api/questions/batch/delete  批量删除（只删自己的）
- POST /api/questions/batch/update  批量改分类/难度
- GET /api/questions/recent  最近编辑的题目
- 越权：别人的题目不能被批量操作
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

PASSWORD = "***"


@pytest.fixture(autouse=True)
def clean_db():
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


def _make_question(user_id, subject="数学", grade="高中", difficulty="简单", content="题目"):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            subject=subject,
            grade=grade,
            difficulty=difficulty,
            content_plain=content,
            content_markdown=content,
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        return q.id or 0


def _login(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ================= 分类树 =================





def test_batch_delete(client):
    uid = _make_user("test1")
    q1 = _make_question(uid, content="A")
    q2 = _make_question(uid, content="B")

    token = _login(client, "test1")
    resp = client.post(
        "/api/questions/batch/delete",
        headers=_h(token),
        json={"ids": [q1, q2]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2

    with Session(engine) as session:
        assert session.exec(select(Question)).all() == []


def test_batch_delete_cannot_delete_others(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    q_other = _make_question(uid2, content="别人的")

    token1 = _login(client, "test1")
    resp = client.post(
        "/api/questions/batch/delete",
        headers=_h(token1),
        json={"ids": [q_other]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0
    assert resp.json()["skipped"] == 1

    # 别人的题还在
    with Session(engine) as session:
        assert session.get(Question, q_other) is not None


def test_batch_delete_empty_ids(client):
    uid1 = _make_user("test1")
    token = _login(client, "test1")
    resp = client.post("/api/questions/batch/delete", headers=_h(token), json={"ids": []})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


# ================= 批量改 =================


def test_batch_update(client):
    uid = _make_user("test1")
    q1 = _make_question(uid, subject="数学", difficulty="简单")
    q2 = _make_question(uid, subject="数学", difficulty="简单")

    token = _login(client, "test1")
    resp = client.post(
        "/api/questions/batch/update",
        headers=_h(token),
        json={"ids": [q1, q2], "difficulty": "困难", "subject": "物理"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    with Session(engine) as session:
        for qid in (q1, q2):
            q = session.get(Question, qid)
            assert q.difficulty == "困难"
            assert q.subject == "物理"


def test_batch_update_partial_fields(client):
    """只传 difficulty,其他字段不动"""
    uid = _make_user("test1")
    qid = _make_question(uid, subject="数学", grade="高中", difficulty="简单")

    token = _login(client, "test1")
    client.post(
        "/api/questions/batch/update",
        headers=_h(token),
        json={"ids": [qid], "difficulty": "中等"},
    )
    with Session(engine) as session:
        q = session.get(Question, qid)
        assert q.difficulty == "中等"
        assert q.subject == "数学"
        assert q.grade == "高中"


def test_batch_update_cannot_touch_others(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    q_other = _make_question(uid2, subject="化学")

    token1 = _login(client, "test1")
    resp = client.post(
        "/api/questions/batch/update",
        headers=_h(token1),
        json={"ids": [q_other], "subject": "被改了"},
    )
    assert resp.json()["updated"] == 0
    assert resp.json()["skipped"] == 1
    with Session(engine) as session:
        assert session.get(Question, q_other).subject == "化学"


# ================= 最近编辑 =================


def test_recent_questions(client):
    uid = _make_user("test1")
    _make_question(uid, content="老题")
    q_new = _make_question(uid, content="新题")

    token = _login(client, "test1")
    resp = client.get("/api/questions/recent", headers=_h(token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    # 最近的排前面
    assert items[0]["id"] == q_new


def test_recent_only_own(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    _make_question(uid1, content="我的")
    _make_question(uid2, content="别人的")

    token1 = _login(client, "test1")
    items = client.get("/api/questions/recent", headers=_h(token1)).json()["items"]
    contents = [i["content_plain"] for i in items]
    assert "我的" in contents
    assert "别人的" not in contents
