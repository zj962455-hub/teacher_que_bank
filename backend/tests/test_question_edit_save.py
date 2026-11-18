"""题目「编辑 → 保存」回归测试 — lesson-37

踩过的坑
--------
编辑器以前保存时把 content_markdown 发成**原题内容**（props.withFormulas），
老师改的字被旧值盖回去 —— 界面上「保存成功」，库里纹丝不动。

这几条用例锁住行为：
1. PUT 只带 content_markdown（不带 blocks）→ 正文按老师改的存，纯文本版跟着重算
2. PUT 带 blocks（OCR 一键入库那种）→ 三个内容版本仍由 blocks 推导
3. 版式只认三项
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Question, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "abc123"


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


def _make_question(user_id, markdown="原题内容 $x^2$", blocks_json=""):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            subject="数学",
            question_type="解答题",
            grade="初中",
            difficulty="简单",
            content_plain="原题内容 x²",
            content_markdown=markdown,
            blocks_json=blocks_json,
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


# ================= 保存改动真的落库 =================


def test_update_saves_edited_content(client):
    """老师改了正文 → 库里必须是改后的内容（不是原题内容）"""
    uid = _make_user("test1")
    qid = _make_question(uid)
    token = _login(client, "test1")

    edited = "老师改过的题目：求证 $BE=AD$ 成立"
    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"content_markdown": edited},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert q.content_markdown == edited
        # 纯文本版按改后的正文重算（公式转 Unicode），不是原题的旧值
        assert q.content_plain == "老师改过的题目：求证 BE=AD 成立"


def test_update_keeps_blocks_derived_versions(client):
    """带 blocks 的更新（OCR 一键入库路径）→ 三个版本仍由 blocks 推导"""
    uid = _make_user("test1")
    blocks = [
        {"type": "text", "text": "题干第一行"},
        {"type": "formula", "latex": "x^{2}", "plain": "x²"},
    ]
    qid = _make_question(uid, blocks_json=json.dumps(blocks, ensure_ascii=False))
    token = _login(client, "test1")

    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"blocks": blocks},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert "题干第一行" in q.content_plain
        assert "$x^{2}$" in q.content_markdown


def test_update_layout_accepts_three_options(client):
    """版式只认三项：文字下方右下 / 文字下方左下 / 不显示"""
    uid = _make_user("test1")
    qid = _make_question(uid)
    token = _login(client, "test1")

    for value in ("bottom_right", "bottom_left", "none"):
        resp = client.put(
            f"/api/questions/{qid}",
            headers=_h(token),
            json={"figure_layout": value},
        )
        assert resp.status_code == 200
        with Session(engine) as session:
            assert session.get(Question, qid).figure_layout == value

    # 旧版式不再是可选值 → 回落默认
    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"figure_layout": "bottom_center"},
    )
    assert resp.status_code == 200
    with Session(engine) as session:
        assert session.get(Question, qid).figure_layout == "bottom_right"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
