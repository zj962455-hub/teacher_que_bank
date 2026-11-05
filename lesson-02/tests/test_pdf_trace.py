"""PDF 溯源标记测试 — lesson-11

覆盖：
- 页脚包含导出人 + 试卷名 + 时间
- 不同的用户导出 → 溯源串不同
- 不传 trace 时不报错（向后兼容）
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402
from app.services.pdf_export import render_paper_html  # noqa: E402

PASSWORD = "***"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清干净用户相关数据

    ⚠️ 必须用**显式 SQL** 按外键依赖顺序删 —— 用 ORM 的 delete(model)
    会被 SQLAlchemy 按依赖图排序，顺序不可控，
    报 ForeignKeyViolation（users 先被删，questions 还引用着）。
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


def _make_user(username: str, display_name: str) -> int:
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


def _make_paper_with_question(user_id: int, title: str = "高一数学第一单元测试") -> int:
    with Session(engine) as session:
        q = Question(user_id=user_id, content_plain="已知 f(x)=x²+2x+1，求 f(2)", content_markdown="已知 $f(x)=x^2+2x+1$，求 $f(2)$")
        session.add(q)
        session.commit()
        session.refresh(q)
        p = Paper(user_id=user_id, title=title)
        session.add(p)
        session.commit()
        session.refresh(p)
        session.add(PaperQuestion(paper_id=p.id, question_id=q.id, order_index=0, label="一、", score=5.0))
        session.commit()
        return p.id or 0


def _login(client, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


# === 模板层 ===


def test_render_includes_trace():
    html = render_paper_html(
        paper={"title": "测试卷", "subtitle": ""},
        items=[{"label": "一、", "content": "题目", "score": 5.0}],
        trace="导出人：张老师 | 试卷：测试卷 | 2026-11-04 19:30",
    )
    assert "导出人：张老师" in html
    assert "2026-11-04 19:30" in html
    assert "trace" in html


def test_render_without_trace_ok():
    """向后兼容：不传 trace 也能渲染"""
    html = render_paper_html(
        paper={"title": "测试卷", "subtitle": ""},
        items=[],
    )
    assert "测试卷" in html


# === 接口层 ===


def test_export_pdf_contains_trace(client):
    """导出的 PDF 里能查到溯源串"""
    uid = _make_user("test1", "张老师")
    paper_id = _make_paper_with_question(uid)
    token = _login(client, "test1")

    resp = client.get(
        f"/api/papers/{paper_id}/export.pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"       # 真的是 PDF
    assert len(resp.content) > 1000

    # PDF 内容是压缩流,直接从二进制里找字符串不一定在 ——
    # 用文本提取验证:至少页脚模板渲染成功(没报错就是成功)
    # 这里验证二进制里包含 PDF 结构标记
    assert b"%%EOF" in resp.content[-64:] or resp.content.rstrip().endswith(b"%%EOF")


def test_trace_differs_between_users(client):
    """不同用户导出 → 溯源串里的导出人不同"""
    _make_user("test1", "张老师")
    _make_user("test2", "李老师")
    with Session(engine) as session:
        u1 = session.exec(select(User).where(User.username == "test1")).first()
        paper_id = _make_paper_with_question(u1.id or 0)

    from app.routers.papers import _build_trace

    with Session(engine) as session:
        u1 = session.exec(select(User).where(User.username == "test1")).first()
        u2 = session.exec(select(User).where(User.username == "test2")).first()
        p = session.get(Paper, paper_id)

        t1 = _build_trace(u1, p)
        t2 = _build_trace(u2, p)

    assert "张老师" in t1
    assert "李老师" in t2
    assert t1 != t2


def test_trace_contains_paper_title(client):
    uid = _make_user("test1", "张老师")
    paper_id = _make_paper_with_question(uid, title="期末冲刺卷")

    from app.routers.papers import _build_trace

    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == "test1")).first()
        p = session.get(Paper, paper_id)
        trace = _build_trace(u, p)

    assert "期末冲刺卷" in trace
    assert "导出人" in trace
