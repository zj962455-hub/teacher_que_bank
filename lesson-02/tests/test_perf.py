"""性能回归测试 — lesson-33

锁住三件事（防止以后改回去）：

1. **列表接口不带 blocks** —— 单题 blocks 最多 50 KB，
   50 道题一起返回 = 响应暴涨 7 倍，而列表页根本不用 blocks。
2. **列表接口不 N+1** —— 试卷列表 / 试卷详情 / 统计，
   SQL 条数不随数据量线性增长。
3. **统计接口不拉整表** —— COUNT 交给数据库，不把整表拉进 Python。

用法：cd lesson-02 && ./venv/bin/python -m pytest tests/test_perf.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "abc123456"

# 造多少题/卷
N_QUESTIONS = 60
N_PAPERS = 6
PER_PAPER = 10


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


def _make_data(client, uid):
    """造 N 道题（带 blocks）+ M 张卷"""
    import json as _json

    with Session(engine) as session:
        qs = []
        for i in range(N_QUESTIONS):
            q = Question(
                user_id=uid,
                subject="数学",
                question_type="选择题",
                grade="高一",
                difficulty="简单",
                content_plain=f"第{i}题 求通项公式。",
                content_markdown=f"第{i}题 求 $a_n$ 通项公式。",
                # blocks 每题塞 40 块 —— 真实 OCR 数据就是这么重
                blocks_json=_json.dumps(
                    [{"type": "text", "text": f"第{i}题", "bbox": [10, 20, 300, 60]}] * 40,
                    ensure_ascii=False,
                ),
            )
            session.add(q)
            qs.append(q)
        session.commit()
        for q in qs:
            session.refresh(q)

        for p_i in range(N_PAPERS):
            p = Paper(user_id=uid, title=f"卷{p_i}", subtitle="高一")
            session.add(p)
            session.commit()
            session.refresh(p)
            for j in range(PER_PAPER):
                session.add(PaperQuestion(
                    paper_id=p.id,
                    question_id=qs[(p_i * PER_PAPER + j) % N_QUESTIONS].id,
                    order_index=j,
                    label=f"{j + 1}.",
                    score=5.0,
                ))
            session.commit()


def _count_sql(fn):
    """跑一次函数，数它发了多少条 SQL"""
    counter = {"n": 0}

    def hook(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", hook)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", hook)
    return counter["n"]


# ============================================================
# 1. 列表不带 blocks
# ============================================================

def test_question_list_omits_blocks(client):
    """列表接口不带 blocks —— 每题 blocks 最多 50 KB，50 道题就是 2.5 MB"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/", headers=_h(token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    for item in items:
        assert "blocks" not in item, "列表项不该带 blocks（详情页才有）"


def test_question_detail_still_has_blocks(client):
    """⚠️ 详情接口**必须**带 blocks —— OCR 校对页要靠它溯源"""
    token, uid = _login(client)
    _make_data(client, uid)

    with Session(engine) as session:
        qid = session.exec(text("SELECT id FROM questions LIMIT 1")).first()[0]

    resp = client.get(f"/api/questions/{qid}", headers=_h(token))
    assert resp.status_code == 200
    assert "blocks" in resp.json()
    assert resp.json()["blocks"], "blocks 不该是空数组"


def test_recent_omits_blocks(client):
    """仪表盘「最近编辑」也不要 blocks"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/recent", headers=_h(token))
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert "blocks" not in item


def test_list_response_size_bounded(client):
    """列表响应体积要小 —— 60 道题带 blocks 会到 MB 级"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/", headers=_h(token))
    size = len(resp.content)
    # 60 道题 × 40 block 的 OCR 数据，带上就是好几 MB
    assert size < 200 * 1024, f"列表响应 {size/1024:.0f} KB，太大了（blocks 没剔掉？）"


# ============================================================
# 2. 不 N+1
# ============================================================

def _sql_count_at(client, uid, n_papers, n_per_paper, path_builder):
    """造指定规模的数据，返回该请求发出的 SQL 条数"""
    import json as _json

    with Session(engine) as session:
        qs = []
        for i in range(n_papers * n_per_paper):
            q = Question(
                user_id=uid, subject="数学", question_type="选择题", grade="高一",
                difficulty="简单", content_plain=f"第{i}题 求通项公式。",
                content_markdown=f"第{i}题 求 $a_n$ 通项公式。",
                blocks_json=_json.dumps([{"type": "text", "text": "x", "bbox": [1, 2, 3, 4]}] * 40,
                                        ensure_ascii=False),
            )
            session.add(q)
            qs.append(q)
        session.commit()
        for q in qs:
            session.refresh(q)
        papers = []
        for p_i in range(n_papers):
            p = Paper(user_id=uid, title=f"卷{p_i}", subtitle="高一")
            session.add(p)
            session.commit()
            session.refresh(p)
            for j in range(n_per_paper):
                session.add(PaperQuestion(
                    paper_id=p.id, question_id=qs[(p_i * n_per_paper + j) % len(qs)].id,
                    order_index=j, label=f"{j + 1}.", score=5.0,
                ))
            session.commit()
            papers.append(p.id)

    path = path_builder(papers)
    return _count_sql(lambda: client.get(path, headers=_h(client.token)))


def test_paper_list_sql_count_constant(client):
    """试卷列表：SQL 条数**不随卷数增长**（原来每张卷查一次题数 = N+1）"""
    token, uid = _login(client)
    client.token = token

    small = _sql_count_at(client, uid, 2, 3, lambda p: "/api/papers/")
    _clean_data()
    token2, uid2 = _login(client, "test1")
    client.token = token2
    big = _sql_count_at(client, uid2, 8, 5, lambda p: "/api/papers/")

    assert small == big, f"卷数翻倍但 SQL 从 {small} 变 {big} 条 —— 还是 N+1"


def test_paper_detail_sql_count_constant(client):
    """试卷详情：SQL 条数**不随题数增长**（原来每道题 session.get 一次）"""
    token, uid = _login(client)
    client.token = token

    small = _sql_count_at(client, uid, 1, 3, lambda p: f"/api/papers/{p[0]}")
    _clean_data()
    token2, uid2 = _login(client, "test1")
    client.token = token2
    big = _sql_count_at(client, uid2, 1, 20, lambda p: f"/api/papers/{p[0]}")

    assert small == big, f"题数变多但 SQL 从 {small} 变 {big} 条 —— 还是 N+1"


def test_stats_sql_count_constant(client):
    """统计接口：SQL 条数不随题数增长（原来把整表拉进 Python 再 len）"""
    token, uid = _login(client)

    _make_data(client, uid)
    small = _count_sql(lambda: client.get("/api/auth/stats", headers=_h(token)))
    _clean_data()
    token2, uid2 = _login(client, "test1")
    _make_data(client, uid2)
    big = _count_sql(lambda: client.get("/api/auth/stats", headers=_h(token2)))

    assert small == big, f"数据量变了但 SQL 从 {small} 变 {big} 条"


def _clean_data():
    """清掉探针数据（外键顺序）"""
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


# ============================================================
# 3. COUNT 在数据库里算
# ============================================================

def test_stats_counts_are_correct(client):
    """改完 COUNT 之后数字必须还是对的"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/auth/stats", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["questions"] == N_QUESTIONS
    assert data["papers"] == N_PAPERS


def test_question_list_total_is_correct(client):
    """列表分页的 total 必须还是对的"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/", headers=_h(token))
    assert resp.json()["total"] == N_QUESTIONS

    resp = client.get("/api/questions/?limit=10", headers=_h(token))
    data = resp.json()
    assert data["total"] == N_QUESTIONS
    assert len(data["items"]) == 10


def test_question_list_total_with_filter(client):
    """带筛选时 total 也要对"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/?subject=数学", headers=_h(token))
    assert resp.json()["total"] == N_QUESTIONS

    resp = client.get("/api/questions/?subject=物理", headers=_h(token))
    assert resp.json()["total"] == 0


def test_question_list_total_with_keyword(client):
    """关键词搜索的 total 也要对"""
    token, uid = _login(client)
    _make_data(client, uid)

    resp = client.get("/api/questions/?keyword=通项公式", headers=_h(token))
    assert resp.json()["total"] == N_QUESTIONS

    resp = client.get("/api/questions/?keyword=不存在的词", headers=_h(token))
    assert resp.json()["total"] == 0
