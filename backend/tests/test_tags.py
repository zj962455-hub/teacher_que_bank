"""标签系统测试 — lesson-11

覆盖:
- GET  /api/tags/                 列表 + 题目数统计
- POST /api/tags/                 新建（重名复用）
- PUT  /api/tags/{id}             重命名 / 改颜色
- DELETE /api/tags/{id}           删标签（题保留，解除关联）
- GET  /api/tags/question/{qid}   某题的标签
- PUT  /api/tags/question/{qid}   设置某题的标签（整体替换）
- GET  /api/questions/?tag_ids=   按标签筛选（多标签取交集）
- GET  /api/questions/?sort=&order= 排序
- 隔离：别人的标签/题碰不到
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Question, QuestionTag, Tag, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "Abcd1234"


@pytest.fixture(autouse=True)
def clean_db():
    with Session(engine) as session:
        for sql in (
            "DELETE FROM question_tags",
            "DELETE FROM tags",
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


def _make_question(user_id, content="题目"):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            content_plain=content,
            content_markdown=content,
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        return q.id or 0


def _make_tag(user_id, name, color="#18a058"):
    with Session(engine) as session:
        t = Tag(user_id=user_id, name=name, color=color)
        session.add(t)
        session.commit()
        session.refresh(t)
        return t.id or 0


def _login(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ================= 标签 CRUD =================


def test_create_and_list(client):
    uid = _make_user("test1")
    token = _login(client, "test1")

    resp = client.post("/api/tags/", headers=_h(token), json={"name": "易错题"})
    assert resp.status_code == 200
    tag_id = resp.json()["id"]
    assert resp.json()["reused"] is False

    resp = client.get("/api/tags/", headers=_h(token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "易错题"
    assert items[0]["count"] == 0


def test_create_duplicate_reuses(client):
    uid = _make_user("test1")
    token = _login(client, "test1")

    first = client.post("/api/tags/", headers=_h(token), json={"name": "易错题"}).json()
    second = client.post("/api/tags/", headers=_h(token), json={"name": "易错题"}).json()
    assert first["id"] == second["id"]
    assert second["reused"] is True

    assert len(client.get("/api/tags/", headers=_h(token)).json()["items"]) == 1


def test_create_requires_login(client):
    assert client.post("/api/tags/", json={"name": "x"}).status_code == 401


def test_create_rejects_empty_name(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.post("/api/tags/", headers=_h(token), json={"name": "   "})
    assert resp.status_code == 400


def test_rename_and_color(client):
    uid = _make_user("test1")
    tag_id = _make_tag(uid, "旧名")
    token = _login(client, "test1")

    resp = client.put(f"/api/tags/{tag_id}", headers=_h(token), json={"name": "新名", "color": "#ff0000"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名"
    assert resp.json()["color"] == "#ff0000"


def test_rename_to_existing_name_fails(client):
    uid = _make_user("test1")
    _make_tag(uid, "已存在")
    tag_id = _make_tag(uid, "原来")
    token = _login(client, "test1")

    resp = client.put(f"/api/tags/{tag_id}", headers=_h(token), json={"name": "已存在"})
    assert resp.status_code == 400


def test_delete_tag_keeps_questions(client):
    """删标签 → 题还在,只是没了标签关联"""
    uid = _make_user("test1")
    tag_id = _make_tag(uid, "要删")
    qid = _make_question(uid)
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": [tag_id]})
    resp = client.delete(f"/api/tags/{tag_id}", headers=_h(token))
    assert resp.status_code == 200

    with Session(engine) as session:
        assert session.get(Question, qid) is not None
        links = session.exec(select(QuestionTag)).all()
        assert len(links) == 0


def test_cannot_touch_others_tag(client):
    _make_user("test1")
    uid2 = _make_user("test2")
    tag_id = _make_tag(uid2, "别人的")

    token1 = _login(client, "test1")
    assert client.put(f"/api/tags/{tag_id}", headers=_h(token1), json={"name": "改"}).status_code == 404
    assert client.delete(f"/api/tags/{tag_id}", headers=_h(token1)).status_code == 404


def test_tag_list_only_own(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    _make_tag(uid1, "我的标签")
    _make_tag(uid2, "别人标签")

    token1 = _login(client, "test1")
    items = client.get("/api/tags/", headers=_h(token1)).json()["items"]
    assert [t["name"] for t in items] == ["我的标签"]


# ================= 题目 ↔ 标签 =================


def test_set_and_get_question_tags(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    t2 = _make_tag(uid, "B")
    qid = _make_question(uid)
    token = _login(client, "test1")

    resp = client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": [t1, t2]})
    assert resp.status_code == 200
    assert sorted(resp.json()["tag_ids"]) == sorted([t1, t2])

    resp = client.get(f"/api/tags/question/{qid}", headers=_h(token))
    assert resp.status_code == 200
    assert {t["name"] for t in resp.json()["items"]} == {"A", "B"}


def test_set_question_tags_replaces(client):
    """整体替换 —— 不是追加"""
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    t2 = _make_tag(uid, "B")
    qid = _make_question(uid)
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": [t1]})
    client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": [t2]})

    items = client.get(f"/api/tags/question/{qid}", headers=_h(token)).json()["items"]
    assert [t["name"] for t in items] == ["B"]


def test_clear_question_tags(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    qid = _make_question(uid)
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": [t1]})
    client.put(f"/api/tags/question/{qid}", headers=_h(token), json={"tag_ids": []})

    assert client.get(f"/api/tags/question/{qid}", headers=_h(token)).json()["items"] == []


def test_cannot_tag_foreign_question(client):
    _make_user("test1")
    uid2 = _make_user("test2")
    t1 = _make_tag(uid2, "别人的标签")
    qid = _make_question(uid2)

    token1 = _login(client, "test1")
    assert client.put(f"/api/tags/question/{qid}", headers=_h(token1), json={"tag_ids": [t1]}).status_code == 404


def test_cannot_use_foreign_tag(client):
    """别人的标签 id 传进来 → 静默丢弃,不能给别人的标签挂自己的题"""
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    foreign_tag = _make_tag(uid2, "别人的标签")
    qid = _make_question(uid1)

    token1 = _login(client, "test1")
    resp = client.put(f"/api/tags/question/{qid}", headers=_h(token1), json={"tag_ids": [foreign_tag]})
    assert resp.status_code == 200
    assert resp.json()["tag_ids"] == []


def test_tag_count_in_list(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    q1 = _make_question(uid, "题1")
    q2 = _make_question(uid, "题2")
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{q1}", headers=_h(token), json={"tag_ids": [t1]})
    client.put(f"/api/tags/question/{q2}", headers=_h(token), json={"tag_ids": [t1]})

    items = client.get("/api/tags/", headers=_h(token)).json()["items"]
    assert items[0]["count"] == 2


# ================= 按标签筛选题目 =================


def test_filter_questions_by_tag(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "易错")
    tagged = _make_question(uid, "有标签的题")
    _make_question(uid, "没标签的题")
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{tagged}", headers=_h(token), json={"tag_ids": [t1]})

    resp = client.get(f"/api/questions/?tag_ids={t1}", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["content_plain"] == "有标签的题"


def test_filter_questions_multi_tag_intersection(client):
    """多标签取交集 —— 必须同时有两个标签"""
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    t2 = _make_tag(uid, "B")
    only_a = _make_question(uid, "只有A")
    both = _make_question(uid, "两个都有")
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{only_a}", headers=_h(token), json={"tag_ids": [t1]})
    client.put(f"/api/tags/question/{both}", headers=_h(token), json={"tag_ids": [t1, t2]})

    resp = client.get(f"/api/questions/?tag_ids={t1},{t2}", headers=_h(token))
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["content_plain"] == "两个都有"


def test_filter_questions_no_tag_match(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    _make_question(uid, "别的题")
    token = _login(client, "test1")

    resp = client.get(f"/api/questions/?tag_ids={t1}", headers=_h(token))
    assert resp.json()["total"] == 0


def test_filter_questions_by_foreign_tag(client):
    """别人的标签不该筛出任何东西"""
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    foreign = _make_tag(uid2, "别人的")
    _make_question(uid1, "我的题")
    token1 = _login(client, "test1")

    resp = client.get(f"/api/questions/?tag_ids={foreign}", headers=_h(token1))
    assert resp.json()["total"] == 0


# ================= 排序 =================


def test_sort_by_created_at(client):
    uid = _make_user("test1")
    _make_question(uid, "旧的")
    _make_question(uid, "新的")
    token = _login(client, "test1")

    desc = client.get("/api/questions/?sort=created_at&order=desc", headers=_h(token)).json()
    asc = client.get("/api/questions/?sort=created_at&order=asc", headers=_h(token)).json()
    assert desc["items"][0]["content_plain"] == "新的"
    assert asc["items"][0]["content_plain"] == "旧的"


def test_sort_by_subject(client):
    uid = _make_user("test1")
    with Session(engine) as session:
        for subj, content in (("数学", "数学题"), ("物理", "物理题")):
            session.add(
                Question(
                    user_id=uid,
                    subject=subj,
                    content_plain=content,
                    content_markdown=content,
                )
            )
        session.commit()
    token = _login(client, "test1")

    resp = client.get("/api/questions/?sort=subject&order=asc", headers=_h(token)).json()
    assert [q["subject"] for q in resp["items"]] == ["数学", "物理"]


def test_invalid_sort_falls_back(client):
    """非法排序字段 → 回退到默认,不报错"""
    uid = _make_user("test1")
    _make_question(uid, "题")
    token = _login(client, "test1")

    resp = client.get("/api/questions/?sort=;DROP TABLE users;--", headers=_h(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_sort_with_tag_filter(client):
    uid = _make_user("test1")
    t1 = _make_tag(uid, "A")
    q1 = _make_question(uid, "第一")
    q2 = _make_question(uid, "第二")
    token = _login(client, "test1")

    client.put(f"/api/tags/question/{q1}", headers=_h(token), json={"tag_ids": [t1]})
    client.put(f"/api/tags/question/{q2}", headers=_h(token), json={"tag_ids": [t1]})

    resp = client.get(f"/api/questions/?tag_ids={t1}&sort=created_at&order=desc", headers=_h(token))
    assert resp.json()["total"] == 2
