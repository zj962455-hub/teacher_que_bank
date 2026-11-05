"""上传图片鉴权测试 — lesson-11

覆盖方案 A 的核心：图片不再是静态裸奔
- 上传要登录
- 读图片要登录
- 读别人的图片 → 404（不返 403，避免探测文件名是否存在）
- 文件名带随机后缀（不可预测）
- 目录穿越被拦
"""

import io
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

PASSWORD = "Test1234"

# 1x1 像素 PNG
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000154a24f7d0000000049454e44ae426082"
)


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


def _make_user(username: str) -> int:
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


def _login(client, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _upload(client, token: str, filename: str = "probe.png"):
    return client.post(
        "/api/uploads/",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, io.BytesIO(PNG_BYTES), "image/png")},
    )


# === 上传要登录 ===


def test_upload_requires_login(client):
    resp = client.post(
        "/api/uploads/",
        files={"file": ("probe.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert resp.status_code == 401


def test_upload_success(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = _upload(client, token)
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"].startswith("/api/uploads/")
    # 文件名带随机后缀 → 不可预测
    assert "probe.png" not in data["filename"]


def test_upload_rejects_non_image(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.post(
        "/api/uploads/",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("evil.sh", io.BytesIO(b"#!/bin/sh\nrm -rf /"), "application/x-sh")},
    )
    assert resp.status_code == 400


def test_upload_records_owner(client):
    uid = _make_user("test1")
    token = _login(client, "test1")
    resp = _upload(client, token)
    with Session(engine) as session:
        record = session.exec(select(Upload)).first()
        assert record.user_id == uid
        assert record.filename == resp.json()["filename"]


# === 读图片要登录 ===


def test_read_upload_requires_login(client):
    _make_user("test1")
    token = _login(client, "test1")
    filename = _upload(client, token).json()["filename"]
    # 不带 token → 401
    resp = client.get(f"/api/uploads/{filename}")
    assert resp.status_code == 401


def test_read_own_upload_ok(client):
    _make_user("test1")
    token = _login(client, "test1")
    filename = _upload(client, token).json()["filename"]
    resp = client.get(f"/api/uploads/{filename}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.content == PNG_BYTES


def test_read_other_users_upload_is_404(client):
    _make_user("test1")
    _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    filename = _upload(client, token1).json()["filename"]

    # test2 读 test1 的图 → 404（不是 403 —— 不泄露文件名是否存在）
    resp = client.get(f"/api/uploads/{filename}", headers={"Authorization": f"Bearer {token2}"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "文件不存在"


def test_nonexistent_upload_is_404(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.get("/api/uploads/nonexistent.png", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_path_traversal_blocked(client):
    _make_user("test1")
    token = _login(client, "test1")
    resp = client.get(
        "/api/uploads/..%2F..%2Fetc%2Fpasswd",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# === 列表只列自己的 ===


def test_upload_list_only_own(client):
    _make_user("test1")
    _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    _upload(client, token1, "a.png")
    _upload(client, token2, "b.png")

    r1 = client.get("/api/uploads/list", headers={"Authorization": f"Bearer {token1}"}).json()
    r2 = client.get("/api/uploads/list", headers={"Authorization": f"Bearer {token2}"}).json()

    assert len(r1) == 1
    assert len(r2) == 1
    assert r1[0]["original_name"] == "a.png"
    assert r2[0]["original_name"] == "b.png"


def test_upload_list_requires_login(client):
    resp = client.get("/api/uploads/list")
    assert resp.status_code == 401


# === 静态挂载已移除 ===


def test_static_mount_removed(client):
    """旧路径 /uploads/xxx 不再能直接访问（静态挂载已删）"""
    _make_user("test1")
    token = _login(client, "test1")
    filename = _upload(client, token).json()["filename"]

    # 旧路径：nginx 会转给后端，但后端已无 /uploads 路由 → 404
    resp = client.get(f"/uploads/{filename}")
    assert resp.status_code == 404
