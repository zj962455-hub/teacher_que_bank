"""题库 Excel 导出测试 — lesson-11

覆盖：
- GET /api/questions/export/excel  返回可读的 xlsx
- 只导当前用户的题
- 需要登录
"""

import io
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


def _make_question(user_id, content="题目", subject="数学"):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            subject=subject,
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


# ================= 导出 =================


def test_export_requires_login(client):
    resp = client.get("/api/questions/export/excel")
    assert resp.status_code == 401


def test_export_returns_xlsx(client):
    uid = _make_user("test1")
    _make_question(uid, "第一道题")

    token = _login(client, "test1")
    resp = client.get("/api/questions/export/excel", headers=_h(token))
    assert resp.status_code == 200
    # 是 xlsx（zip 容器）
    assert resp.content[:2] == b"PK"
    assert len(resp.content) > 500
    # 附件头
    disp = resp.headers.get("content-disposition", "")
    assert "attachment" in disp


def test_export_content_is_readable(client):
    """用 openpyxl 读回来,确认表头和数据都在"""
    from openpyxl import load_workbook

    uid = _make_user("test1")
    _make_question(uid, "第一道题")
    _make_question(uid, "第二道题")

    token = _login(client, "test1")
    resp = client.get("/api/questions/export/excel", headers=_h(token))

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    assert rows[0][0] == "ID"
    assert rows[0][1] == "学科"
    assert len(rows) == 3          # 表头 + 2 道题
    texts = [str(r[5]) for r in rows[1:]]
    assert "第一道题" in texts
    assert "第二道题" in texts


def test_export_only_own_questions(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    _make_question(uid1, "我的题")
    _make_question(uid2, "别人的题")

    token1 = _login(client, "test1")
    resp = client.get("/api/questions/export/excel", headers=_h(token1))

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    texts = [str(r[5]) for r in rows[1:]]
    assert "我的题" in texts
    assert "别人的题" not in texts
    assert len(rows) == 2           # 表头 + 1 道


def test_export_empty_is_still_valid_file(client):
    """没有题时也要给出合法文件(表头在),不能 500"""
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.get("/api/questions/export/excel", headers=_h(token))
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"

# ================= 备份接口 =================


def test_backup_returns_json(client):
    """备份接口返回合法 JSON,含题目/试卷/关联三块"""
    uid = _make_user("test1")
    _make_question(uid, "备份的题")

    token = _login(client, "test1")
    resp = client.get("/api/questions/export/backup", headers=_h(token))
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")

    data = resp.json()
    assert data["user"]["username"] == "test1"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["content_plain"] == "备份的题"
    assert "papers" in data
    assert "paper_questions" in data
    assert "exported_at" in data


def test_backup_requires_login(client):
    resp = client.get("/api/questions/export/backup")
    assert resp.status_code == 401


def test_backup_only_own_data(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    _make_question(uid1, "我的题")
    _make_question(uid2, "别人的题")

    token1 = _login(client, "test1")
    data = client.get("/api/questions/export/backup", headers=_h(token1)).json()
    plains = [q["content_plain"] for q in data["questions"]]
    assert "我的题" in plains
    assert "别人的题" not in plains


def test_backup_empty_is_valid(client):
    """没数据时也要返回合法 JSON,不能 500"""
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.get("/api/questions/export/backup", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["questions"] == []
    assert data["papers"] == []
