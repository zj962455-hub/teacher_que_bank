"""试卷题目批量重排测试 — lesson-11

覆盖拖拽排序的后端接口:
- PUT /api/papers/{id}/questions/order  按传入顺序重排
- 不在列表里的题排到后面(order_index 不重复)
- 别人的卷不能改
- 路由顺序:静态路径 /order 必须在 /{pq_id} 前面
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


def _make_user(username):
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=username,
            password_hash=hash_password(PASSWORD),
            must_change_password=False,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _make_paper_with_questions(user_id, count=3):
    """造一张卷,加 count 道题,返回 (paper_id, [pq_id...])"""
    with Session(engine) as session:
        p = Paper(user_id=user_id, title="测试卷")
        session.add(p)
        session.commit()
        session.refresh(p)

        pq_ids = []
        for i in range(count):
            q = Question(user_id=user_id, content_plain=f"题{i}", content_markdown=f"题{i}")
            session.add(q)
            session.commit()
            session.refresh(q)

            pq = PaperQuestion(
                paper_id=p.id,
                question_id=q.id,
                order_index=i,
                label="",
                score=5.0,
            )
            session.add(pq)
            session.commit()
            session.refresh(pq)
            pq_ids.append(pq.id or 0)

        return p.id or 0, pq_ids


def _login(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _order_map(paper_id):
    with Session(engine) as session:
        rows = session.exec(
            select(PaperQuestion)
            .where(PaperQuestion.paper_id == paper_id)
            .order_by(PaperQuestion.order_index)
        ).all()
        return [r.id for r in rows]


def test_reorder_changes_order(client):
    uid = _make_user("test1")
    paper_id, pq_ids = _make_paper_with_questions(uid, 3)
    token = _login(client, "test1")

    # 倒序
    reversed_ids = list(reversed(pq_ids))
    resp = client.put(
        f"/api/papers/{paper_id}/questions/order",
        headers=_h(token),
        json={"ids": reversed_ids},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert _order_map(paper_id) == reversed_ids


def test_reorder_keeps_all_questions(client):
    """传入的 ids 不全时,剩下的题排到后面,不能丢"""
    uid = _make_user("test1")
    paper_id, pq_ids = _make_paper_with_questions(uid, 3)
    token = _login(client, "test1")

    resp = client.put(
        f"/api/papers/{paper_id}/questions/order",
        headers=_h(token),
        json={"ids": [pq_ids[2], pq_ids[0]]},
    )
    assert resp.status_code == 200

    order = _order_map(paper_id)
    assert len(order) == 3                    # 一题都没丢
    assert order[:2] == [pq_ids[2], pq_ids[0]]  # 前两个按传入顺序
    assert pq_ids[1] in order[2:]              # 剩下的排后面


def test_reorder_requires_login(client):
    uid = _make_user("test1")
    paper_id, pq_ids = _make_paper_with_questions(uid, 1)
    resp = client.put(
        f"/api/papers/{paper_id}/questions/order",
        json={"ids": pq_ids},
    )
    assert resp.status_code == 401


def test_reorder_cannot_touch_others_paper(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    paper_id, pq_ids = _make_paper_with_questions(uid2, 2)

    token1 = _login(client, "test1")
    resp = client.put(
        f"/api/papers/{paper_id}/questions/order",
        headers=_h(token1),
        json={"ids": list(reversed(pq_ids))},
    )
    assert resp.status_code == 404
    # 顺序没变
    assert _order_map(paper_id) == pq_ids


def test_reorder_ignores_foreign_pq_ids(client):
    """传了别的卷的 pq_id → 忽略,不能把它拖进来"""
    uid = _make_user("test1")
    paper_id, pq_ids = _make_paper_with_questions(uid, 2)
    other_paper, other_pqs = _make_paper_with_questions(uid, 1)

    token = _login(client, "test1")
    resp = client.put(
        f"/api/papers/{paper_id}/questions/order",
        headers=_h(token),
        json={"ids": [pq_ids[1], other_pqs[0], pq_ids[0]]},
    )
    assert resp.status_code == 200

    order = _order_map(paper_id)
    assert len(order) == 2                     # 外来的没进来
    assert other_pqs[0] not in order
    assert order[0] == pq_ids[1]
