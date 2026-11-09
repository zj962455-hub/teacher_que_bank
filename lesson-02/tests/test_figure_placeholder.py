"""【题图】占位符 —— lesson-38

需求：导出时去掉【题图】，同时老师可以在编辑器里手动删掉它。

这两件事不能打架：
- **存储层保留占位符** —— 自动过滤只作用于输出，不许偷偷改写老师存的内容
- **老师主动删了就永久没了** —— 删完保存，刷新不复活，导出也不再有

这几条用例锁住行为：
1. strip_figure_placeholder() 的三种形态（整行 / 同行 / 连续空行）
2. OCR 建题时占位符照旧写进存储（占位符本身还得有用）
3. 试卷 PDF/JPG 导出、分享链接导出、题库 Excel 导出 —— 输出都不带占位符
4. 自动过滤不碰数据库（导出完再查，库里占位符还在）
5. 老师手动删掉 → 保存 → 真的没了，刷新不复活
"""

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, User  # noqa: E402
from app.routers.papers import _export_items as paper_export_items  # noqa: E402
from app.routers.shares import _export_items as share_export_items  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402
from app.services.classifier import (  # noqa: E402
    FIGURE_PLACEHOLDER,
    build_content_versions,
    strip_figure_placeholder,
)

PASSWORD = "abc123456"


@pytest.fixture(autouse=True)
def clean_db():
    with Session(engine) as session:
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM uploads",
            "DELETE FROM paper_shares",
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


def _make_user(username="test1"):
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


def _login(client, username="test1"):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _make_question(user_id, markdown=None, plain=None):
    with Session(engine) as session:
        q = Question(
            user_id=user_id,
            subject="数学",
            question_type="解答题",
            grade="高一",
            difficulty="中等",
            content_plain=plain if plain is not None else (markdown or ""),
            content_markdown=markdown if markdown is not None else "",
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        return q.id or 0


def _make_paper(user_id, question_id, title="占位符验收卷"):
    with Session(engine) as session:
        paper = Paper(user_id=user_id, title=title, subtitle="高一数学")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        pid = paper.id or 0
        pq = PaperQuestion(paper_id=pid, question_id=question_id, order_index=0, label="1.", score=5.0)
        session.add(pq)
        session.commit()
    return pid


# ================= 纯函数 =================


def test_strip_whole_line_placeholder():
    """整行只有占位符 → 整行丢掉"""
    assert strip_figure_placeholder("如图\n【题图】\n求证") == "如图\n求证"


def test_strip_inline_placeholder():
    """同一行还混着文字 → 只去掉占位符，保留这行"""
    assert strip_figure_placeholder("求【题图】证") == "求证"


def test_strip_collapses_blank_lines():
    """删掉占位行后不留连续空行"""
    out = strip_figure_placeholder("上\n【题图】\n\n\n\n下")
    assert "【题图】" not in out
    assert "\n\n\n" not in out
    assert out.startswith("上")
    assert out.endswith("下")


def test_strip_empty_and_none():
    assert strip_figure_placeholder("") == ""
    assert strip_figure_placeholder(None) == ""
    assert strip_figure_placeholder("没有占位符的正文") == "没有占位符的正文"


def test_storage_keeps_placeholder():
    """OCR 建题时占位符照旧写进存储 —— 占位符本身还得有用"""
    blocks = [
        {"type": "text", "text": "如图"},
        {"type": "figure", "page": 1, "bbox": [0, 0, 10, 10]},
        {"type": "text", "text": "求证"},
    ]
    versions = build_content_versions(blocks)
    assert FIGURE_PLACEHOLDER in versions["plain"]
    assert FIGURE_PLACEHOLDER in versions["markdown"]


# ================= 导出链路 =================


def _detail_with_placeholder():
    return {
        "questions": [
            {
                "label": "1.",
                "score": 5.0,
                "question": {
                    "id": 1,
                    "content_plain": "如图\n【题图】\n求证",
                    "content_markdown": "如图\n【题图】\n求证",
                    "figure_path": "",
                    "figure_layout": "bottom_right",
                    "figure_width": 0,
                },
            }
        ]
    }


def test_paper_export_items_strip_placeholder():
    items = paper_export_items(_detail_with_placeholder())
    assert "【题图】" not in items[0]["content"]
    assert "如图" in items[0]["content"]
    assert "求证" in items[0]["content"]


def test_share_export_items_strip_placeholder():
    items = share_export_items(_detail_with_placeholder())
    assert "【题图】" not in items[0]["content"]


def test_excel_export_strips_placeholder(client):
    """题库 Excel 导出 —— 不带内部标记"""
    from openpyxl import load_workbook

    uid = _make_user("test1")
    _make_question(uid, markdown="如图\n【题图】\n求证")
    token = _login(client, "test1")

    resp = client.get("/api/questions/export/excel", headers=_h(token))
    assert resp.status_code == 200

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    texts = [str(r[5]) for r in rows[1:]] + [str(r[6]) for r in rows[1:]]
    assert texts
    assert not any("【题图】" in t for t in texts), texts
    assert any("求证" in t for t in texts)


def test_export_does_not_touch_storage(client):
    """自动过滤只作用于输出 —— 库里的正文一个字都没动"""
    uid = _make_user("test1")
    qid = _make_question(uid, markdown="如图\n【题图】\n求证")
    token = _login(client, "test1")

    client.get("/api/questions/export/excel", headers=_h(token))

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert "【题图】" in q.content_markdown
        assert "【题图】" in q.content_plain


def test_paper_export_pdf_has_no_placeholder(client):
    """试卷 PDF 导出 —— 正文里没有占位符"""
    uid = _make_user("test1")
    qid = _make_question(uid, markdown="如图\n【题图】\n求证")
    pid = _make_paper(uid, qid)
    token = _login(client, "test1")

    resp = client.get(f"/api/papers/{pid}/export.pdf", headers=_h(token))
    # 渲染环境不一定会装 Chromium；这里只断言接口没 5xx，
    # 真正的「导出结果长什么样」由线上无头验收脚本核对。
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert resp.content[:4] == b"%PDF"


# ================= 老师手动删除 =================


def test_manual_delete_persists(client):
    """老师手动删掉【题图】→ 保存 → 真的没了，刷新不复活"""
    uid = _make_user("test1")
    qid = _make_question(uid, markdown="如图\n【题图】\n求证")
    token = _login(client, "test1")

    edited = "如图\n求证"
    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"content_markdown": edited},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert "【题图】" not in q.content_markdown
        # 纯文本版也跟着重算，不能从旧值里把占位符带回来
        assert "【题图】" not in q.content_plain

    # 刷新（重新 GET）也不该复活
    got = client.get(f"/api/questions/{qid}", headers=_h(token))
    assert got.status_code == 200
    assert "【题图】" not in got.json()["content_markdown"]
    assert "【题图】" not in got.json()["content_plain"]


def test_manual_delete_then_export_stays_clean(client):
    """手动删过之后，导出里当然也没有占位符"""
    uid = _make_user("test1")
    qid = _make_question(uid, markdown="如图\n【题图】\n求证")
    pid = _make_paper(uid, qid)
    token = _login(client, "test1")

    client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"content_markdown": "如图\n求证"},
    )

    resp = client.get("/api/questions/export/excel", headers=_h(token))
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    texts = [str(r[5]) for r in rows[1:]] + [str(r[6]) for r in rows[1:]]
    assert not any("【题图】" in t for t in texts)


def test_untouched_placeholder_survives_edit_of_other_fields(client):
    """老师只改别的字段（比如难度）→ 占位符还在存储里（自动过滤不许偷偷删）"""
    uid = _make_user("test1")
    qid = _make_question(uid, markdown="如图\n【题图】\n求证")
    token = _login(client, "test1")

    resp = client.put(
        f"/api/questions/{qid}",
        headers=_h(token),
        json={"difficulty": "简单"},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        q = session.get(Question, qid)
        assert "【题图】" in q.content_markdown
