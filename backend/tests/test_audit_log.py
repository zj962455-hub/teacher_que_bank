"""
操作审计日志 —— 端到端测试（lesson-41 · 公安备案安全评估）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_audit_log.py -v

测什么
------
1. 登录后调接口 → audit_logs 里有一条，且**用户账号对得上**（这是 nginx 日志做不到的）
2. 未登录的访问照样记（user_id 为空，但有记录）—— 未认证访问尝试本身要能审计
3. 安全评估要求的字段齐全：操作时间 / 操作类型 / 源地址 / 目标地址 / 源端口 / 客户端特征
4. 源地址取真实客户端 IP，而不是 nginx 代理的 127.0.0.1
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, User, create_tables  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

ACCOUNT = "audit_test_user"
PASSWORD = "Audit1234"


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
                display_name="审计测试",
                password_hash=hash_password(PASSWORD),
                is_active=True,
                must_change_password=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        yield row


def _latest_audit():
    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(20)
        ).all()
        return list(rows)


def test_audit_records_logged_in_user(client, user):
    """登录后操作 → 审计记录里有账号"""
    r = client.post(
        "/api/auth/login",
        json={"account": ACCOUNT, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    client.get(
        "/api/questions/",
        headers={"Authorization": f"Bearer {token}"},
    )

    rows = _latest_audit()
    hit = next(
        (
            x
            for x in rows
            if x.username == ACCOUNT and x.path.startswith("/api/questions")
        ),
        None,
    )
    assert hit is not None, "审计表里没有这次操作"
    assert hit.user_id == user.id
    assert hit.method == "GET"
    assert hit.action == "题目管理"
    assert hit.status_code == 200


def test_audit_records_unauthenticated_access(client):
    """未登录的访问照样记（user_id 为空）"""
    client.get("/api/questions/")
    rows = _latest_audit()
    hit = next(
        (x for x in rows if x.path.startswith("/api/questions") and x.user_id is None),
        None,
    )
    assert hit is not None, "未认证访问没有被记录"
    assert hit.status_code == 401


def test_audit_has_required_fields(client, user):
    """安全评估要求的字段必须齐全"""
    r = client.post(
        "/api/auth/login",
        json={"account": ACCOUNT, "password": PASSWORD},
    )
    token = r.json()["token"]
    client.get(
        "/api/questions/",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "AuditProbe/1.0",
            "X-Real-IP": "203.0.113.77",
        },
    )

    rows = _latest_audit()
    hit = next(
        (x for x in rows if x.username == ACCOUNT and x.path.startswith("/api/questions")),
        None,
    )
    assert hit is not None

    # 操作时间
    assert hit.created_at is not None
    # 操作类型
    assert hit.method and hit.path and hit.action
    # 网络源地址（取真实客户端 IP，不是代理的 127.0.0.1）
    assert hit.client_ip == "203.0.113.77", hit.client_ip
    # 目标地址
    assert hit.target_path.startswith("/api/questions")
    assert hit.target_host
    # 网络源端口（列存在，测试客户端不一定有端口）
    assert hit.client_port is not None
    # 客户端硬件特征
    assert hit.user_agent == "AuditProbe/1.0", hit.user_agent
    # 结果与耗时
    assert hit.status_code == 200
    assert hit.duration_ms >= 0


def test_audit_login_action_is_labeled(client, user):
    """登录动作本身也要能被识别出来"""
    client.post(
        "/api/auth/login",
        json={"account": ACCOUNT, "password": PASSWORD},
    )
    rows = _latest_audit()
    hit = next((x for x in rows if x.path.startswith("/api/auth/login")), None)
    assert hit is not None, "登录操作没有被记录"
    assert hit.action == "账号登录"
    assert hit.username == ACCOUNT
