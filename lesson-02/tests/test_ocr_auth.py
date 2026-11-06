"""OCR 鉴权 + 归属校验测试 — lesson-35

修的三个洞
----------
1. **三个 OCR 接口零鉴权** —— ``POST /api/ocr/``、``/api/ocr/status/{id}``、
   ``/api/ocr/history`` 之前一个都没鉴权，公网可调：
   - 任何人能触发 OCR → 打满 OCR 服务（2 并发）就是拒绝服务
   - ``/api/ocr/history`` 返回**所有用户**的识别记录 → 别人的试卷内容泄露

2. **路径穿越** —— 之前拿 URL 直接拼磁盘路径
   （``image_url.lstrip("/").replace("uploads/", "", 1)``），
   ``/uploads/../../etc/x.png`` 能读到服务器上任意图片。

3. **越权** —— 之前任何登录用户拿 task_id 就能把**别人**的 OCR 结果入库。

口径
----
越权一律 **404（不返 403）** —— 跟 ``/api/uploads/{filename}`` 既有口径一致：
不让外人用状态码差异探测出某个 id / 文件名存不存在。

另外：``/uploads/x.png``（静态挂载时代的旧格式）和
``/api/uploads/x.png``（lesson-11 鉴权路由的新格式）都要能认 ——
前端现在发的是后者，之前只认前者 → 老师根本识别不了。
"""

import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Question, Upload, User  # noqa: E402
from app.routers.ocr import extract_filename  # noqa: E402
from app.routers.upload import UPLOAD_DIR  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402
from app.services import ocr_store  # noqa: E402

PASSWORD = "Test1234"

# 1x1 像素 PNG
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000154a24f7d0000000049454e44ae426082"
)


# === fixtures ===


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


@pytest.fixture(autouse=True)
def clean_ocr_tasks(tmp_path, monkeypatch):
    """OCR 任务隔离

    - OCR_STORE_DIR 指到 tmp —— 测试别往真实的 uploads/ocr/ 里写垃圾
    - TASKS 清空（测试结束后还原）——
      app.routers.ocr 里 ``from ... import TASKS as tasks`` 拿到的是**同一个 dict**，
      原地 clear 两边都看得见
    """
    monkeypatch.setattr(ocr_store, "OCR_STORE_DIR", tmp_path / "ocr")
    saved = dict(ocr_store.TASKS)
    ocr_store.TASKS.clear()
    yield
    ocr_store.TASKS.clear()
    ocr_store.TASKS.update(saved)


@pytest.fixture
def client():
    return TestClient(app)


# === helpers ===


def _make_user(username: str, *, is_admin: bool = False) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=username,
            password_hash=hash_password(PASSWORD),
            must_change_password=False,
            is_active=True,
            is_admin=is_admin,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _login(client, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(client, token: str, filename: str = "probe.png") -> dict:
    resp = client.post(
        "/api/uploads/",
        headers=_auth(token),
        files={"file": (filename, io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_task(task_id: str, *, user_id: int | None = None, status: str = "completed") -> dict:
    """造一条 OCR 任务记录（落盘 + 进内存）

    user_id 传 None → 模拟**历史遗留记录**（上线前那批，没有 user_id 字段）。
    """
    record = {
        "task_id": task_id,
        "status": status,
        "result": {
            "blocks": [{"type": "text", "text": "已知两边之和为 10"}],
            "stats": {"elapsed_ms": 1},
        },
        "image_url": f"/api/uploads/{task_id}.png",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    if user_id is not None:
        record["user_id"] = user_id
    ocr_store.save_task(task_id, record)
    return record


# === 1. 三个接口都要登录 ===


def test_start_ocr_requires_login(client):
    resp = client.post("/api/ocr/", json={"image_url": "/api/uploads/x.png"})
    assert resp.status_code == 401


def test_status_requires_login(client):
    resp = client.get("/api/ocr/status/whatever")
    assert resp.status_code == 401


def test_history_requires_login(client):
    resp = client.get("/api/ocr/history")
    assert resp.status_code == 401


# === 2. 两种 URL 前缀都能解析成同一个裸文件名 ===


def test_extract_filename_accepts_both_prefixes():
    assert extract_filename("/uploads/x.png") == "x.png"
    assert extract_filename("/api/uploads/x.png") == "x.png"
    # 带查询串也认
    assert extract_filename("/api/uploads/x.png?v=1") == "x.png"


@pytest.mark.parametrize(
    "bad",
    [
        "/uploads/../../etc/x.png",
        "/api/uploads/../x.png",
        "/api/uploads/..",
        "/api/uploads/a/b.png",
        "/api/uploads/",
        "/etc/passwd",
        "x.png",
        "",
        "/uploads/..%2F..%2Fetc%2Fx.png",
    ],
)
def test_extract_filename_rejects_unsafe(bad):
    assert extract_filename(bad) is None


def test_old_format_url_still_works(client):
    """旧格式 /uploads/x.png（静态挂载时代）也要能跑 —— 历史数据里还有"""
    _make_user("test1")
    token = _login(client, "test1")
    data = _upload(client, token)
    old_url = "/uploads/" + data["filename"]

    resp = client.post(
        "/api/ocr/", headers=_auth(token), json={"image_url": old_url}
    )
    assert resp.status_code == 200, resp.text


def test_new_format_url_works(client):
    """新格式 /api/uploads/x.png —— 前端现在发的是这个（之前 404）"""
    _make_user("test1")
    token = _login(client, "test1")
    data = _upload(client, token)
    assert data["url"].startswith("/api/uploads/")

    resp = client.post(
        "/api/ocr/", headers=_auth(token), json={"image_url": data["url"]}
    )
    assert resp.status_code == 200, resp.text


# === 3. 图片归属：别人的图 → 404 ===


def test_other_users_image_is_404(client):
    _make_user("test1")
    _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    url = _upload(client, token1)["url"]

    resp = client.post("/api/ocr/", headers=_auth(token2), json={"image_url": url})
    # 404 而不是 403 —— 不泄露「这个文件名存不存在」
    assert resp.status_code == 404
    assert resp.json()["detail"] == "图片不存在"


def test_unregistered_file_is_404(client):
    """磁盘上有、但 uploads 表里没有 → 404

    这条堵的是「直接拿 URL 拼路径」——
    不在表里的文件（谁放进去的不知道）一律不给用。
    """
    _make_user("test1")
    token = _login(client, "test1")

    stray = UPLOAD_DIR / "stray_not_in_table.png"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(PNG_BYTES)
    try:
        resp = client.post(
            "/api/ocr/",
            headers=_auth(token),
            json={"image_url": "/api/uploads/stray_not_in_table.png"},
        )
        assert resp.status_code == 404
    finally:
        stray.unlink(missing_ok=True)


# === 4. 路径穿越 → 404 且一个字节都没读 ===


def test_path_traversal_blocked(client, monkeypatch):
    _make_user("test1")
    token = _login(client, "test1")

    touched: list[str] = []

    def _spy(path):
        touched.append(str(path))
        return {"blocks": [], "stats": {}}

    monkeypatch.setattr("app.routers.ocr.validate_image", _spy)
    monkeypatch.setattr("app.routers.ocr.recognize", _spy)

    bad_urls = [
        "/uploads/../../../../usr/share/pixmaps/htop.png",
        "/api/uploads/../../etc/x.png",
        "/api/uploads/../x.png",
        "/uploads/..%2F..%2Fetc%2Fx.png",
        "/api/uploads/....//x.png",
        "/api/uploads/sub/dir/x.png",
    ]
    for bad in bad_urls:
        resp = client.post("/api/ocr/", headers=_auth(token), json={"image_url": bad})
        assert resp.status_code == 404, f"{bad} → {resp.status_code}"

    # ⚠️ 关键断言：validate_image / recognize 一次都没被调
    #    —— 说明压根没去碰文件系统
    assert touched == []


def test_path_traversal_does_not_read_sentinel(client, tmp_path, monkeypatch):
    """造一个 uploads/ 之外的图片文件 —— 穿越请求不该把它读出来"""
    _make_user("test1")
    token = _login(client, "test1")

    sentinel = tmp_path / "sentinel.png"
    sentinel.write_bytes(PNG_BYTES)

    reads: list[str] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        reads.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    resp = client.post(
        "/api/ocr/",
        headers=_auth(token),
        json={"image_url": "/uploads/../../../../tmp/sentinel.png"},
    )
    assert resp.status_code == 404
    assert not any("sentinel" in p for p in reads)


# === 5. OCR 任务归属 ===


def test_status_of_other_users_task_is_404(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    _make_task("task-b", user_id=uid2, status="processing")

    assert client.get("/api/ocr/status/task-b", headers=_auth(token2)).status_code == 200
    resp = client.get("/api/ocr/status/task-b", headers=_auth(token1))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"


def test_history_only_returns_own_records(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    _make_task("task-a", user_id=uid1)
    _make_task("task-b", user_id=uid2)

    ids1 = [
        i["task_id"]
        for i in client.get("/api/ocr/history", headers=_auth(token1)).json()["items"]
    ]
    ids2 = [
        i["task_id"]
        for i in client.get("/api/ocr/history", headers=_auth(token2)).json()["items"]
    ]

    assert "task-a" in ids1
    assert "task-b" not in ids1
    assert "task-b" in ids2
    assert "task-a" not in ids2


def test_legacy_record_hidden_from_users_visible_to_admin(client):
    """历史遗留记录（没有 user_id 字段）→ 普通用户看不到，管理员看得到"""
    _make_user("test1")
    _make_user("boss", is_admin=True)
    token1 = _login(client, "test1")
    token_admin = _login(client, "boss")
    _make_task("legacy-task")  # 没有 user_id

    ids_user = [
        i["task_id"]
        for i in client.get("/api/ocr/history", headers=_auth(token1)).json()["items"]
    ]
    ids_admin = [
        i["task_id"]
        for i in client.get("/api/ocr/history", headers=_auth(token_admin)).json()["items"]
    ]

    assert "legacy-task" not in ids_user
    assert "legacy-task" in ids_admin

    # status 同样口径
    assert client.get("/api/ocr/status/legacy-task", headers=_auth(token1)).status_code == 404
    assert (
        client.get("/api/ocr/status/legacy-task", headers=_auth(token_admin)).status_code
        == 200
    )


def test_user_id_persisted_to_disk_and_reloaded(tmp_path):
    """user_id 要跟着 task 落盘，重启恢复后归属还在"""
    _make_task("task-a", user_id=42)

    files = list((tmp_path / "ocr").glob("*.json"))
    assert files, "OCR 记录应该落盘了"
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["user_id"] == 42

    # 模拟重启：从磁盘重新加载
    reloaded = ocr_store._load_all()
    assert reloaded["task-a"]["user_id"] == 42


# === 6. from-ocr 入库也要校验归属 ===


def test_from_ocr_other_users_task_is_404(client):
    uid1 = _make_user("test1")
    uid2 = _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")
    _make_task("task-b", user_id=uid2)

    resp = client.post("/api/questions/from-ocr/task-b", headers=_auth(token1))
    assert resp.status_code == 404

    # 库里不能多出题目
    with Session(engine) as session:
        assert session.exec(select(Question)).all() == []


def test_from_ocr_own_task_ok(client):
    uid1 = _make_user("test1")
    token1 = _login(client, "test1")
    _make_task("task-a", user_id=uid1)

    resp = client.post("/api/questions/from-ocr/task-a", headers=_auth(token1))
    assert resp.status_code == 200, resp.text
    assert resp.json()["question"]["ocr_task_id"] == "task-a"

    with Session(engine) as session:
        questions = session.exec(select(Question)).all()
        assert len(questions) == 1
        assert questions[0].user_id == uid1


def test_from_ocr_admin_can_use_others_task(client):
    uid2 = _make_user("test2")
    _make_user("boss", is_admin=True)
    token2 = _login(client, "test2")
    token_admin = _login(client, "boss")
    _make_task("task-b", user_id=uid2)

    resp = client.post("/api/questions/from-ocr/task-b", headers=_auth(token_admin))
    assert resp.status_code == 200, resp.text


# === 7. 正常路径：本人上传自己的图 → OCR 能跑起来 ===


def test_own_upload_runs_ocr(client, monkeypatch):
    uid1 = _make_user("test1")
    token1 = _login(client, "test1")
    url = _upload(client, token1)["url"]

    # ⚠️ mock 掉真正的 OCR 调用 —— 别真去连 paddleocr
    calls: list[str] = []

    def fake_recognize(path: str) -> dict:
        calls.append(str(path))
        return {
            "blocks": [{"type": "text", "text": "已知两边之和为 10"}],
            "stats": {"elapsed_ms": 12, "model": "fake"},
        }

    monkeypatch.setattr("app.routers.ocr.recognize", fake_recognize)

    resp = client.post("/api/ocr/", headers=_auth(token1), json={"image_url": url})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    task_id = body["task_id"]

    # 后台任务在 TestClient 里是同步跑完的
    record = ocr_store.TASKS[task_id]
    assert record["status"] == "completed"
    assert record["user_id"] == uid1
    assert calls, "recognize 应该被调到了"

    # 自己的任务查得到
    st = client.get(f"/api/ocr/status/{task_id}", headers=_auth(token1))
    assert st.status_code == 200
    assert st.json()["status"] == "completed"

    # 自己的历史里能看到
    ids = [
        i["task_id"]
        for i in client.get("/api/ocr/history", headers=_auth(token1)).json()["items"]
    ]
    assert task_id in ids


def test_own_upload_old_and_new_url_same_file(client, monkeypatch):
    """同一个文件，两种 URL 写法 → 都指向同一个裸文件名"""
    _make_user("test1")
    token1 = _login(client, "test1")
    data = _upload(client, token1)

    new_url = data["url"]                     # /api/uploads/xxx.png
    old_url = "/uploads/" + data["filename"]  # /uploads/xxx.png

    assert extract_filename(new_url) == extract_filename(old_url) == data["filename"]
