"""
内容安全与处置链路 —— 测试（lesson-42 · 公安备案安全评估）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_content_safety.py -v

测什么
------
1. 昵称（显示名）校验：正常昵称放行；违法违规内容、引流信息、不可见字符拒绝
2. 改资料接口与注册接口都会拒绝非法昵称
3. 上传的图片**能真的删掉**（文件从磁盘消失 + 数据库记录消失）
4. 还被题目引用的图片 → 拒绝删（409），避免把别的题搞成裂图
5. 删题目会连带清掉它引用的图片文件（原来只删数据库行，文件永远留盘）
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Question, Upload, User, create_tables  # noqa: E402
from app.routers.auth import _validated_display_name  # noqa: E402
from app.services.auth import hash_password  # noqa: E402
from app.services.content import check_display_name  # noqa: E402
from app.services.paths import uploads_dir  # noqa: E402

ACCOUNT = "safety_test_user"
PASSWORD = "Safety1234"


@pytest.fixture(scope="module", autouse=True)
def _ensure_table():
    create_tables()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def user():
    with Session(engine) as session:
        row = session.exec(select(User).where(User.username == ACCOUNT)).first()
        if row is None:
            row = User(
                username=ACCOUNT,
                display_name="安全测试",
                password_hash=hash_password(PASSWORD),
                is_active=True,
                must_change_password=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        yield row


def _token(client):
    r = client.post(
        "/api/auth/login", json={"account": ACCOUNT, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ================= 昵称校验 =================


def test_normal_display_names_pass():
    for name in ["张老师", "李老师（小教）", "王老师 2026", "Teacher·A", "张😀"]:
        assert check_display_name(name) == [], name


def test_illegal_content_rejected():
    cases = [
        "色情教学资源",
        "代开发票联系",
        "博彩代理",
        "https://example.com/xxx",
        "微信：abc12345",
    ]
    for name in cases:
        problems = check_display_name(name)
        assert problems, name


def test_invisible_chars_rejected():
    problems = check_display_name("张\u200b老师")
    assert problems
    assert any("不可见" in p for p in problems)


def test_empty_and_too_long():
    assert check_display_name("")
    assert check_display_name("x" * 60)


def test_validated_helper_falls_back_to_masked_phone():
    """昵称留空是允许的 —— 兜底用脱敏手机号"""
    out = _validated_display_name("", "13800138000")
    # mask_phone 输出 138****8000（打码，不是明文）
    assert out == "138****8000", out
    assert "13800138000" not in out


def test_profile_api_rejects_illegal_name(client, user):
    token = _token(client)
    r = client.patch(
        "/api/auth/profile",
        json={"display_name": "代开发票请联系"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400, r.text


def test_profile_api_accepts_normal_name(client, user):
    token = _token(client)
    r = client.patch(
        "/api/auth/profile",
        json={"display_name": "张老师"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


# ================= 上传文件删除 =================


def _upload_png(client, token):
    """造一个 1x1 的 PNG 上传"""
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )
    r = client.post(
        "/api/uploads/",
        files={"file": ("t.png", png, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["filename"]


def test_upload_can_be_deleted(client, user):
    token = _token(client)
    filename = _upload_png(client, token)
    path = uploads_dir() / filename
    assert path.is_file(), "上传后文件应存在"

    r = client.delete(
        f"/api/uploads/{filename}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert not path.is_file(), "删除后文件应从磁盘消失"

    with Session(engine) as session:
        row = session.exec(
            select(Upload).where(Upload.filename == filename)
        ).first()
        assert row is None, "uploads 表记录也应删除"


def test_delete_refuses_when_referenced_by_question(client, user):
    """还被题目引用 → 409，不许删（否则别的题变裂图）"""
    token = _token(client)
    filename = _upload_png(client, token)

    with Session(engine) as session:
        q = Question(
            subject="数学",
            question_type="选择题",
            grade="初一",
            difficulty="中",
            content_plain="1+1=?",
            content_markdown="1+1=?",
            blocks_json="[]",
            image_path=f"/api/uploads/{filename}",
            ocr_task_id="",
            user_id=user.id or 0,
        )
        session.add(q)
        session.commit()

    r = client.delete(
        f"/api/uploads/{filename}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, r.text


def test_delete_question_removes_its_image_file(client, user):
    """删题目要连带清掉图片文件 —— 原来只删数据库行，文件永远留盘"""
    token = _token(client)
    filename = _upload_png(client, token)
    path = uploads_dir() / filename
    assert path.is_file()

    with Session(engine) as session:
        q = Question(
            subject="数学",
            question_type="选择题",
            grade="初一",
            difficulty="中",
            content_plain="1+1=?",
            content_markdown="1+1=?",
            blocks_json="[]",
            image_path=f"/api/uploads/{filename}",
            ocr_task_id="",
            user_id=user.id or 0,
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        qid = q.id

    r = client.delete(
        f"/api/questions/{qid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert not path.is_file(), "删题目后图片文件应被清掉"
