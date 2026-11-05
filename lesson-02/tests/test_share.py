"""分享链接测试 — lesson-24

覆盖：
- 生成 / 列出 / 吊销（管理线，要登录，只能操作自己的卷）
- 公开线：看卷子、下 PDF、下 JPG（**不用登录**）
- 过期链接失效、吊销链接失效
- 公开接口不泄露任何用户字段
"""

import io
import sys
import zipfile
from datetime import datetime, timedelta, timezone
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
    """每个测试前清干净数据

    ⚠️ 必须用**显式 SQL** 按外键依赖顺序删 —— 用 ORM 的 delete(model)
    会被 SQLAlchemy 按依赖图排序，顺序不可控，报 ForeignKeyViolation。
    """
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

        pq = PaperQuestion(paper_id=pid, question_id=qid, order_index=0, label="一、", score=5.0)
        session.add(pq)
        session.commit()
    return pid


# ============================================================
# 管理线
# ============================================================

def test_create_share_returns_token(client):
    """生成链接 → 返回 token + 过期时间 + 状态 active"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    resp = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token"], "没返回 token"
    assert data["state"] == "active"
    assert data["paper_id"] == pid
    assert data["expires_at"]


def test_create_share_requires_login(client):
    """没登录 → 401"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    resp = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24})
    assert resp.status_code == 401


def test_create_share_other_user_404(client):
    """分享别人的卷 → 404（不能把别人的卷链接出去）"""
    token_a, uid_a = _login(client, "test1")
    token_b, uid_b = _login(client, "test2")
    pid = _make_paper_with_question(uid_a)

    resp = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token_b))
    assert resp.status_code == 404


def test_create_share_empty_paper_400(client):
    """空卷 → 400（生成的链接打开是空白页，没意义）"""
    token, uid = _login(client)
    with Session(engine) as session:
        paper = Paper(user_id=uid, title="空卷")
        session.add(paper)
        session.commit()
        session.refresh(paper)
        pid = paper.id or 0

    resp = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token))
    assert resp.status_code == 400


def test_create_share_expire_hours_out_of_range_400(client):
    """有效期超范围 → 400"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    resp = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 99999}, headers=_h(token))
    assert resp.status_code == 400


def test_list_shares(client):
    """列出这张卷的链接"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token))
    client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 48}, headers=_h(token))

    resp = client.get(f"/api/papers/{pid}/shares", headers=_h(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len({i["token"] for i in data["items"]}) == 2, "两条链接 token 应该不同"


def test_revoke_share_then_public_404(client):
    """吊销后公开访问 → 404"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)

    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()
    share_id = created["id"]
    share_token = created["token"]

    # 吊销前能打开
    assert client.get(f"/api/shares/{share_token}").status_code == 200

    resp = client.delete(f"/api/papers/{pid}/shares/{share_id}", headers=_h(token))
    assert resp.status_code == 200

    # 吊销后打不开了
    assert client.get(f"/api/shares/{share_token}").status_code == 404


# ============================================================
# 公开线（不用登录）
# ============================================================

def test_public_view_no_login(client):
    """公开查看：不用登录就能看卷子"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()

    resp = client.get(f"/api/shares/{created['token']}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["title"] == "期中测试卷"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["label"] == "一、"


def test_public_view_unknown_token_404(client):
    """不存在的 token → 404"""
    resp = client.get("/api/shares/does-not-exist")
    assert resp.status_code == 404


def test_public_view_expired_404(client):
    """过期链接 → 404"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 1}, headers=_h(token)).json()

    # 把过期时间拨到过去（模拟到期）
    with Session(engine) as session:
        from app.models import PaperShare

        record = session.get(PaperShare, created["id"])
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(record)
        session.commit()

    assert client.get(f"/api/shares/{created['token']}").status_code == 404


def test_public_view_does_not_leak_user_fields(client):
    """公开接口不能吐任何用户字段（owner id / 用户名 / 邮箱）"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()

    resp = client.get(f"/api/shares/{created['token']}")
    assert resp.status_code == 200
    body = resp.text
    for leak in ("user_id", "owner", "username", "password", "email"):
        assert leak not in body, f"公开响应里漏了 {leak}: {body}"


def test_public_view_counts_access(client):
    """每次访问记 view_count / last_viewed_at（审计）"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()

    client.get(f"/api/shares/{created['token']}")
    client.get(f"/api/shares/{created['token']}")

    listing = client.get(f"/api/papers/{pid}/shares", headers=_h(token)).json()
    item = listing["items"][0]
    assert item["view_count"] == 2
    assert item["last_viewed_at"]


def test_public_export_pdf(client):
    """公开下 PDF"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()

    resp = client.get(f"/api/shares/{created['token']}/export.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF", "不是合法 PDF"


def test_public_export_jpg(client):
    """公开下 JPG（ZIP）"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 24}, headers=_h(token)).json()

    resp = client.get(f"/api/shares/{created['token']}/export.jpg")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert names, "ZIP 里没有文件"
        assert all(n.lower().endswith(".jpg") for n in names), names


def test_public_export_expired_404(client):
    """过期链接下不了 PDF"""
    token, uid = _login(client)
    pid = _make_paper_with_question(uid)
    created = client.post(f"/api/papers/{pid}/shares", json={"expire_hours": 1}, headers=_h(token)).json()

    with Session(engine) as session:
        from app.models import PaperShare

        record = session.get(PaperShare, created["id"])
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.add(record)
        session.commit()

    assert client.get(f"/api/shares/{created['token']}/export.pdf").status_code == 404
    assert client.get(f"/api/shares/{created['token']}/export.jpg").status_code == 404
