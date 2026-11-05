"""统一错误契约测试 — lesson-32

覆盖：
- 所有错误出口返回**同一个形状**：{detail, code, request_id}
- detail **永远是字符串**（旧的开发模式 422 返数组 → 前端渲染成空白）
- 每个响应都带 X-Request-ID 响应头
- 机器码正确：401 → auth.*，403 → auth.forbidden，422 → request.validation_failed，500 → server.internal
- ApiHTTPException 能带自定义机器码
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Paper, PaperQuestion, Question, Session_, Upload, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402
from app.services.errors import ApiHTTPException  # noqa: E402

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


# ============================================================
# 形状
# ============================================================

def test_401_has_unified_shape(client):
    """未登录 → 统一形状 + auth.required 机器码"""
    resp = client.get("/api/papers/")
    assert resp.status_code == 401
    body = resp.json()
    assert set(body) >= {"detail", "code", "request_id"}
    assert isinstance(body["detail"], str), "detail 必须是字符串"
    assert body["code"] == "auth.required"
    assert body["request_id"]


def test_404_has_unified_shape(client):
    """不存在的资源 → 统一形状"""
    token, uid = _login(client)
    resp = client.get("/api/papers/999999", headers=_h(token))
    assert resp.status_code == 404
    body = resp.json()
    assert isinstance(body["detail"], str)
    assert body["code"]
    assert body["request_id"]


def test_422_detail_is_string(client):
    """参数校验失败 → detail 仍是字符串（不是数组！）

    ⚠️ 旧行为：开发模式下 detail 是 FastAPI 的 errors() 数组 →
    前端 `{{ error.data.detail }}` 渲染数组 → 页面显示 "[object Object]" 或空白。
    """
    token, uid = _login(client)
    resp = client.post("/api/papers/", json={"title": 12345}, headers=_h(token))
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], str), f"detail 是数组: {body['detail']}"
    assert body["code"] == "request.validation_failed"


def test_request_id_header_present(client):
    """每个响应都带 X-Request-ID（浏览器 Network 面板能对上日志）"""
    resp = client.get("/api/papers/")
    assert resp.headers.get("X-Request-ID")
    assert resp.headers["X-Request-ID"] == resp.json()["request_id"]


def test_request_id_echoes_incoming(client):
    """上游带了 X-Request-ID 就沿用（网关/链路追踪能串起来）"""
    resp = client.get("/api/papers/", headers={"X-Request-ID": "upstream-abc123"})
    assert resp.json()["request_id"] == "upstream-abc123"


def test_403_code(client):
    """账号被停用 → auth.forbidden"""
    token, uid = _login(client)
    with Session(engine) as session:
        user = session.get(User, uid)
        user.is_active = False
        session.add(user)
        session.commit()

    resp = client.get("/api/papers/", headers=_h(token))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


def test_500_has_unified_shape(client, monkeypatch):
    """未捕获异常 → server.internal + request_id（细节不外泄）

    ⚠️ TestClient 默认 ``raise_server_exceptions=True`` —— 异常会**直接抛回测试**，
    根本走不到我们的 handler。所以这个用例要单独建一个不重抛的 client。
    """
    # 造一个必然炸的接口
    @app.get("/__boom_test__")
    def boom():
        raise RuntimeError("内部细节不该外泄 SECRET_VALUE")

    quiet = TestClient(app, raise_server_exceptions=False)
    try:
        resp = quiet.get("/__boom_test__")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "server.internal"
        assert body["request_id"]
        assert "SECRET_VALUE" not in resp.text, "内部细节外泄了"
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__boom_test__"]


def test_api_http_exception_custom_code(client):
    """ApiHTTPException 能带自定义机器码"""
    @app.get("/__custom_code_test__")
    def custom():
        raise ApiHTTPException(status_code=418, detail="我是茶壶", code="custom.teapot")

    try:
        resp = client.get("/__custom_code_test__")
        assert resp.status_code == 418
        body = resp.json()
        assert body["detail"] == "我是茶壶"
        assert body["code"] == "custom.teapot"
        assert body["request_id"]
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__custom_code_test__"]


def test_all_errors_have_same_keys(client):
    """不同类型的错误，键集合必须一致（前端才能一套代码解析全平台）"""
    token, uid = _login(client)

    cases = [
        client.get("/api/papers/"),                      # 401
        client.get("/api/papers/999999", headers=_h(token)),  # 404
        client.post("/api/papers/", json={"title": 1}, headers=_h(token)),  # 422
    ]
    keysets = {frozenset(r.json().keys()) for r in cases}
    assert len(keysets) == 1, f"错误体键不一致: {keysets}"
