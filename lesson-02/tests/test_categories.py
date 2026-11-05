"""章节分类（真表）测试 — lesson-11

覆盖:
- GET  /api/categories/            树 + 题目统计（含子分类）
- GET  /api/categories/flat        扁平列表
- POST /api/categories/            新建（顶层/子级）
- PUT  /api/categories/{id}        重命名 / 移动
- DELETE /api/categories/{id}      删除（子分类上提、题目失去归属但保留）
- POST /api/categories/reorder     拖拽排序
- GET  /api/questions/?category_id=  按分类筛选（含子分类）
- 隔离：别人的分类不能动
- 防环：不能把分类移到自己的子分类下
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
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


def _make_category(user_id, name, parent_id=None):
    with Session(engine) as session:
        c = Category(user_id=user_id, name=name, parent_id=parent_id)
        session.add(c)
        session.commit()
        session.refresh(c)
        return c.id or 0


def _make_question(user_id, content="题目", category_id=None):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            content_plain=content,
            content_markdown=content,
            category_id=category_id,
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


# ================= 建 / 读 =================


def test_create_and_read_tree(client):
    uid = _make_user("test1")
    token = _login(client, "test1")

    resp = client.post("/api/categories/", headers=_h(token), json={"name": "高中数学"})
    assert resp.status_code == 200
    parent_id = resp.json()["id"]

    resp = client.post(
        "/api/categories/",
        headers=_h(token),
        json={"name": "函数与导数", "parent_id": parent_id},
    )
    assert resp.status_code == 200
    child_id = resp.json()["id"]

    tree = client.get("/api/categories/", headers=_h(token)).json()["tree"]
    assert len(tree) == 1
    assert tree[0]["name"] == "高中数学"
    assert tree[0]["children"][0]["name"] == "函数与导数"


def test_create_requires_login(client):
    assert client.post("/api/categories/", json={"name": "x"}).status_code == 401


def test_create_rejects_empty_name(client):
    uid = _make_user("test1")
    token = _login(client, "test1")
    resp = client.post("/api/categories/", headers=_h(token), json={"name": "  "})
    assert resp.status_code == 400


def test_tree_counts_questions(client):
    uid = _make_user("test1")
    parent_id = _make_category(uid, "高中数学")
    child_id = _make_category(uid, "函数", parent_id)

    _make_question(uid, "题1", parent_id)
    _make_question(uid, "题2", child_id)
    _make_question(uid, "题3", child_id)

    token = _login(client, "test1")
    tree = client.get("/api/categories/", headers=_h(token)).json()["tree"]
    node = tree[0]
    # 自己的 1 道 + 子分类 2 道
    assert node["count"] == 3
    assert node["own_count"] == 1
    assert node["children"][0]["count"] == 2


def test_flat_list(client):
    uid = _make_user("test1")
    parent_id = _make_category(uid, "高中数学")
    _make_category(uid, "函数", parent_id)

    token = _login(client, "test1")
    flat = client.get("/api/categories/flat", headers=_h(token)).json()
    assert len(flat) == 2
    assert {f["name"] for f in flat} == {"高中数学", "函数"}


# ================= 改 / 删 =================


def test_rename(client):
    uid = _make_user("test1")
    cid = _make_category(uid, "旧名字")
    token = _login(client, "test1")

    resp = client.put(f"/api/categories/{cid}", headers=_h(token), json={"name": "新名字"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名字"


def test_delete_keeps_questions(client):
    """删分类 → 题还在,只是失去归属"""
    uid = _make_user("test1")
    cid = _make_category(uid, "要删的")
    qid = _make_question(uid, "保留的题", cid)

    token = _login(client, "test1")
    resp = client.delete(f"/api/categories/{cid}", headers=_h(token))
    assert resp.status_code == 200

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert q is not None
        assert q.category_id is None


def test_delete_lifts_children(client):
    """删父分类 → 子分类上提到上一层,不跟着删"""
    uid = _make_user("test1")
    parent_id = _make_category(uid, "父")
    child_id = _make_category(uid, "子", parent_id)

    token = _login(client, "test1")
    client.delete(f"/api/categories/{parent_id}", headers=_h(token))

    with Session(engine) as session:
        child = session.get(Category, child_id)
        assert child is not None
        assert child.parent_id is None


def test_cannot_move_into_own_descendant(client):
    """防环:不能把父分类移到自己的子分类下"""
    uid = _make_user("test1")
    parent_id = _make_category(uid, "父")
    child_id = _make_category(uid, "子", parent_id)

    token = _login(client, "test1")
    resp = client.put(
        f"/api/categories/{parent_id}",
        headers=_h(token),
        json={"parent_id": child_id},
    )
    assert resp.status_code == 400


def test_cannot_touch_others_category(client):
    _make_user("test1")
    uid2 = _make_user("test2")
    cid = _make_category(uid2, "别人的")

    token1 = _login(client, "test1")
    assert client.put(f"/api/categories/{cid}", headers=_h(token1), json={"name": "改了"}).status_code == 404
    assert client.delete(f"/api/categories/{cid}", headers=_h(token1)).status_code == 404


# ================= 拖拽排序 =================


def test_reorder(client):
    uid = _make_user("test1")
    a = _make_category(uid, "A")
    b = _make_category(uid, "B")
    c = _make_category(uid, "C")

    token = _login(client, "test1")
    resp = client.post(
        "/api/categories/reorder",
        headers=_h(token),
        json={"parent_id": None, "ids": [c, a, b]},
    )
    assert resp.status_code == 200

    flat = client.get("/api/categories/flat", headers=_h(token)).json()
    assert [f["id"] for f in flat] == [c, a, b]


def test_reorder_requires_login(client):
    uid = _make_user("test1")
    cid = _make_category(uid, "A")
    resp = client.post("/api/categories/reorder", json={"ids": [cid]})
    assert resp.status_code == 401


def test_reorder_ignores_foreign_ids(client):
    """传了别人的分类 id → 忽略"""
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    mine = _make_category(uid1, "我的")
    other = _make_category(uid2, "别人的")

    token1 = _login(client, "test1")
    client.post("/api/categories/reorder", headers=_h(token1), json={"ids": [other, mine]})

    flat = client.get("/api/categories/flat", headers=_h(token1)).json()
    ids = [f["id"] for f in flat]
    assert mine in ids
    assert other not in ids


# ================= 按分类筛题 =================


def test_filter_questions_by_category_includes_children(client):
    uid = _make_user("test1")
    parent_id = _make_category(uid, "高中数学")
    child_id = _make_category(uid, "函数", parent_id)

    _make_question(uid, "父级题", parent_id)
    _make_question(uid, "子级题", child_id)
    _make_question(uid, "别的题", None)

    token = _login(client, "test1")
    resp = client.get(f"/api/questions/?category_id={parent_id}", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    plains = [q["content_plain"] for q in data["items"]]
    assert "父级题" in plains
    assert "子级题" in plains        # 含子分类
    assert "别的题" not in plains


# ================= 移到顶层 / 题目挂章节 =================


def test_move_to_root(client):
    """显式传 parent_id=null → 移到顶层"""
    uid = _make_user("test1")
    parent_id = _make_category(uid, "父")
    child_id = _make_category(uid, "子", parent_id)

    token = _login(client, "test1")
    resp = client.put(f"/api/categories/{child_id}", headers=_h(token), json={"parent_id": None})
    assert resp.status_code == 200

    with Session(engine) as session:
        child = session.get(Category, child_id)
        assert child.parent_id is None


def test_rename_only_keeps_parent(client):
    """只改名字 → 父级不变"""
    uid = _make_user("test1")
    parent_id = _make_category(uid, "父")
    child_id = _make_category(uid, "子", parent_id)

    token = _login(client, "test1")
    resp = client.put(f"/api/categories/{child_id}", headers=_h(token), json={"name": "新名"})
    assert resp.status_code == 200

    with Session(engine) as session:
        child = session.get(Category, child_id)
        assert child.name == "新名"
        assert child.parent_id == parent_id


def test_question_can_hang_on_category(client):
    """新建题目时带 category_id"""
    uid = _make_user("test1")
    cid = _make_category(uid, "函数")

    token = _login(client, "test1")
    resp = client.post(
        "/api/questions/",
        headers=_h(token),
        json={"content_plain": "带章节的题", "category_id": cid},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == cid


def test_question_rejects_foreign_category(client):
    """不能把题挂到别人的分类上"""
    _make_user("test1")
    uid2 = _make_user("test2")
    other = _make_category(uid2, "别人的")

    token = _login(client, "test1")
    resp = client.post(
        "/api/questions/",
        headers=_h(token),
        json={"content_plain": "题", "category_id": other},
    )
    assert resp.status_code == 400


def test_batch_update_category(client):
    """批量改章节"""
    uid = _make_user("test1")
    cid = _make_category(uid, "函数")
    q1 = _make_question(uid, "题1")
    q2 = _make_question(uid, "题2")

    token = _login(client, "test1")
    resp = client.post(
        "/api/questions/batch/update",
        headers=_h(token),
        json={"ids": [q1, q2], "category_id": cid},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    with Session(engine) as session:
        for qid in (q1, q2):
            assert session.get(Question, qid).category_id == cid


def test_update_question_can_clear_category(client):
    """把题从章节里摘出来"""
    uid = _make_user("test1")
    cid = _make_category(uid, "函数")
    qid = _make_question(uid, "题", cid)

    token = _login(client, "test1")
    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"category_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None
