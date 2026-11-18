"""
配合监管与执法的工作机制 —— 测试（lesson-42 · 公安备案安全评估）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_compliance.py -v

测什么
------
1. 审计日志导出：管理员能导（CSV 表头与数据齐全）
2. 非管理员被 403 挡住（接口层，不是靠前端隐藏）
3. 按条件筛选生效（按账号、按 IP）
4. 调阅台账：登记 → 能查到
5. CSV 注入防护：以 = 开头的单元格被转义
"""

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    RegulatoryRequest,
    User,
    create_tables,
)
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Compliance1234"


@pytest.fixture(scope="module", autouse=True)
def _ensure_table():
    create_tables()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _mk_user(username: str, admin: bool) -> int:
    with Session(engine) as session:
        row = session.exec(select(User).where(User.username == username)).first()
        if row is None:
            row = User(
                username=username,
                display_name="合规测试",
                password_hash=hash_password(PASSWORD),
                is_active=True,
                is_admin=admin,
                must_change_password=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return row.id or 0


def _token(client, username):
    r = client.post(
        "/api/auth/login", json={"account": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _seed_audit(account: str, ip: str) -> None:
    with Session(engine) as session:
        session.add(
            AuditLog(
                user_id=None,
                username=account,
                method="GET",
                path="/api/questions/",
                action="题目管理",
                client_ip=ip,
                client_port="51234",
                target_host="tqb.lanhu-lab.top",
                target_path="/api/questions/",
                user_agent="Probe/1.0",
                status_code=200,
                duration_ms=12,
            )
        )
        session.commit()


def test_export_requires_admin(client):
    """非管理员 → 403（接口层挡，不是靠前端隐藏入口）"""
    plain = "plain_" + uuid.uuid4().hex[:8]
    _mk_user(plain, admin=False)
    token = _token(client, plain)
    r = client.get(
        "/api/compliance/audit/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


def test_admin_can_export_audit_csv(client):
    """管理员导出：CSV 表头齐全、有数据、带 BOM"""
    admin_name = "adm_" + uuid.uuid4().hex[:8]
    _mk_user(admin_name, admin=True)
    token = _token(client, admin_name)
    _seed_audit(admin_name, "198.51.100.5")

    r = client.get(
        "/api/compliance/audit/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    text = r.content.decode("utf-8")
    assert text.startswith("\ufeff"), "应带 BOM（Excel 打开中文不乱码）"
    for col in [
        "操作时间",
        "操作账号",
        "操作类型",
        "网络源地址",
        "网络源端口",
        "目标地址",
        "客户端特征",
    ]:
        assert col in text, col
    assert admin_name in text


def test_export_filters_by_account(client):
    """按账号筛选生效"""
    admin_name = "adm2_" + uuid.uuid4().hex[:8]
    _mk_user(admin_name, admin=True)
    token = _token(client, admin_name)
    target = "target_" + uuid.uuid4().hex[:8]
    _seed_audit(target, "203.0.113.9")

    r = client.get(
        f"/api/compliance/audit/export?account={target}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8")
    assert target in text
    assert admin_name not in text


def test_regulatory_request_ledger(client):
    """调阅台账：登记 → 能查到"""
    admin_name = "adm3_" + uuid.uuid4().hex[:8]
    _mk_user(admin_name, admin=True)
    token = _token(client, admin_name)

    payload = {
        "authority": "某市公安局网络安全保卫支队",
        "requester": "张某某（警号 0XXXX）",
        "basis": "网络安全检查调取证据通知书（公网安检字〔2026〕第 12 号）",
        "scope": "2026-11-01 至 2026-11-18 的操作日志",
        "data_provided": "audit_logs.csv 共 166 条",
        "channel": "平台导出",
        "receipt_no": "回执 2026-1118-01",
    }
    r = client.post(
        "/api/compliance/requests",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] > 0

    r2 = client.get(
        "/api/compliance/requests",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert any(i["receipt_no"] == "回执 2026-1118-01" for i in items)

    with Session(engine) as session:
        row = session.exec(
            select(RegulatoryRequest).where(
                RegulatoryRequest.receipt_no == "回执 2026-1118-01"
            )
        ).first()
        assert row is not None
        assert row.authority == payload["authority"]


def test_csv_injection_is_escaped():
    """CSV 注入防护：以 = 开头的单元格要加前缀"""
    from app.services.compliance import audit_logs_to_csv

    row = AuditLog(
        username="=cmd|'/c calc'!A1",
        method="GET",
        path="/api/x",
        action="其他操作",
        client_ip="1.2.3.4",
        client_port="1",
        target_host="h",
        target_path="/api/x",
        user_agent="UA",
        status_code=200,
        duration_ms=1,
    )
    text = audit_logs_to_csv([row])
    assert "=cmd" not in text.replace("'=cmd", "")
    assert "'=cmd" in text


def test_compliance_action_mapping():
    """合规相关路径要归到「合规与监管配合」，不能全叫「其他操作」"""
    from app.services.audit import resolve_action

    assert resolve_action("/api/compliance/audit/export") == "合规与监管配合"
    assert resolve_action("/api/compliance/requests") == "合规与监管配合"
    # 不影响其他既有映射
    assert resolve_action("/api/auth/login") == "账号登录"
    assert resolve_action("/api/questions/") == "题目管理"
