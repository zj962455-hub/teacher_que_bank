"""试卷 JPG 导出测试 — lesson-23

覆盖：
- GET /api/papers/{id}/export.jpg  返回 ZIP，里面是每页一张 JPG
- 试卷没题目 → 400
- 别人的试卷 → 404（数据隔离）
- 需要登录
"""

import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "abc123456"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清干净用户相关数据

    ⚠️ 必须用**显式 SQL** 按外键依赖顺序删 —— 用 ORM 的 delete(model)
    会被 SQLAlchemy 按依赖图排序，顺序不可控，报 ForeignKeyViolation。
    """
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


def _login(client, username="test1"):
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
        uid = user.id or 0
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"], uid


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _make_paper_with_question(user_id):
    """造一张带一道题的卷，返回 paper_id"""
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            subject="数学",
            question_type="选择题",
            grade="高一",
            difficulty="简单",
            content_plain="已知等差数列的前 n 项和为 S_n = n^2 + n，求通项公式。",
            content_markdown="已知等差数列的前 $n$ 项和为 $S_n = n^2 + n$，求通项公式。",
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        qid = q.id or 0

        paper = Paper(user_id=user_id, title="期中测试卷", subtitle="高一数学")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        pid = paper.id or 0

        pq = PaperQuestion(paper_id=pid, question_id=qid, order_index=0, label="1.", score=5.0)
        session.add(pq)
        session.commit()
    return pid


def test_export_jpg_returns_zip_with_images(client):
    """导出 JPG → ZIP，里有 JPG 图片"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    resp = client.get(f"/api/papers/{pid}/export.jpg", headers=_h(token))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    disp = resp.headers.get("content-disposition", "")
    assert "attachment" in disp

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert names, "ZIP 里没有文件"
        assert all(n.lower().endswith(".jpg") for n in names), names
        # JPEG magic bytes
        data = zf.read(names[0])
        assert data[:3] == b"\xff\xd8\xff", "不是合法 JPEG"


def test_export_jpg_empty_paper_400(client):
    """空试卷 → 400"""
    token, uid = _login(client)
    with Session(engine) as session:
        paper = Paper(user_id=uid, title="空卷")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        pid = paper.id or 0

    resp = client.get(f"/api/papers/{pid}/export.jpg", headers=_h(token))
    assert resp.status_code == 400


def test_export_jpg_other_user_404(client):
    """别人的卷 → 404（数据隔离）"""
    token_a, uid_a = _login(client, "test1")
    token_b, uid_b = _login(client, "test2")
    pid = _make_paper_with_question(uid_a)

    resp = client.get(f"/api/papers/{pid}/export.jpg", headers=_h(token_b))
    assert resp.status_code == 404


def test_export_jpg_requires_login(client):
    """没登录 → 401"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    resp = client.get(f"/api/papers/{pid}/export.jpg")
    assert resp.status_code == 401
