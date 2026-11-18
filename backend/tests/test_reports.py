"""
举报受理闭环 —— 测试（lesson-43 · 公安备案 · 安全评估第五条第（六）项）

跑法：
    cd backend
    venv/bin/python -m pytest tests/test_reports.py -v

测什么
------
1. 公开提交：未登录也能举报（官方要的「公开举报、渠道畅通」）
2. 参数校验：类型不合法 / 什么都没填 → 400
3. 进展查询：凭受理编号能查到；编号不对 → 404
4. 隐私：进展查询**不泄露**举报人姓名、联系方式、来源 IP
5. 权限：普通用户调列表/处置 → 403（接口层，不是靠前端隐藏）
6. 处置：管理员把状态改成已处置 → 结论回填，举报人查得到
7. 处置动作：停用账号真的停用，且其会话被注销
8. 限流：同一 IP 一小时内超上限 → 429
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
from app.models import Report, Session_, User, create_tables  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

PASSWORD = "Report1234"
FAKE_IP = "198.51.100.77"


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
                display_name="举报测试",
                password_hash=hash_password(PASSWORD),
                is_active=True,
                is_admin=admin,
                must_change_password=False,
                allow_password_change=True,
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


def _submit(client, ip=FAKE_IP, **over):
    payload = {
        "target_type": "question",
        "target_id": 1,
        "target_desc": "某道题",
        "reason": "illegal",
        "detail": "这道题里有违法有害内容",
        "reporter_name": "匿名访客",
        "reporter_contact": "visitor@example.com",
    }
    payload.update(over)
    return client.post("/api/reports", json=payload, headers={"X-Real-IP": ip})


# ============ 1. 公开提交 ============


def test_anonymous_can_submit_report(client):
    """未登录也能举报 —— 公开分享页的访客没有账号，强制登录就堵死了渠道"""
    r = _submit(client, ip="198.51.100.1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["report_no"].startswith("R")
    assert body["status"] == "pending"
    assert body["status_label"] == "待受理"


def test_submit_requires_detail_or_desc(client):
    """既没填对象也没填说明 → 400"""
    r = _submit(client, ip="198.51.100.2", detail="", target_desc="")
    assert r.status_code == 400, r.text


def test_submit_rejects_bad_reason(client):
    """举报类型不在允许列表 → 400"""
    r = _submit(client, ip="198.51.100.3", reason="hackers")
    assert r.status_code == 400, r.text


def test_submit_rejects_bad_target_type(client):
    """举报对象类型不在允许列表 → 400"""
    r = _submit(client, ip="198.51.100.4", target_type="../../etc")
    assert r.status_code == 400, r.text


# ============ 2. 进展查询 ============


def test_track_by_report_no(client):
    """凭受理编号能查到进展；编号不存在 → 404"""
    r = _submit(client, ip="198.51.100.5")
    no = r.json()["report_no"]

    t = client.get("/api/reports/track/" + no)
    assert t.status_code == 200, t.text
    assert t.json()["report_no"] == no
    assert t.json()["status"] == "pending"

    miss = client.get("/api/reports/track/RNOTEXIST123")
    assert miss.status_code == 404, miss.text


def test_track_does_not_leak_reporter_info(client):
    """进展查询不泄露举报人姓名/联系方式/来源 IP（那是内部信息）"""
    r = _submit(client, ip="198.51.100.6")
    no = r.json()["report_no"]
    body = client.get("/api/reports/track/" + no).json()
    for leak in ("reporter_name", "reporter_contact", "source_ip", "reporter_user_id"):
        assert leak not in body, leak


# ============ 3. 权限 ============


def test_list_requires_admin(client):
    """普通用户调举报列表 → 403"""
    plain = "plain_" + uuid.uuid4().hex[:8]
    _mk_user(plain, admin=False)
    token = _token(client, plain)
    r = client.get("/api/reports", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


def test_handle_requires_admin(client):
    """普通用户调处置接口 → 403"""
    plain = "plain2_" + uuid.uuid4().hex[:8]
    _mk_user(plain, admin=False)
    token = _token(client, plain)
    r = client.patch(
        "/api/reports/1",
        json={"status": "resolved", "handle_note": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


def test_anonymous_cannot_list(client):
    """未登录调列表 → 401"""
    assert client.get("/api/reports").status_code == 401


# ============ 4. 管理员受理与处置 ============


def test_admin_handles_and_reporter_sees_result(client):
    """管理员处置 → 结论回填 → 举报人凭编号查得到"""
    admin_name = "adm_" + uuid.uuid4().hex[:8]
    _mk_user(admin_name, admin=True)
    token = _token(client, admin_name)

    r = _submit(client, ip="198.51.100.7")
    no = r.json()["report_no"]

    listing = client.get("/api/reports", headers={"Authorization": f"Bearer {token}"})
    assert listing.status_code == 200, listing.text
    mine = [x for x in listing.json() if x["report_no"] == no]
    assert mine, "刚提交的举报应出现在列表里"
    rid = mine[0]["id"]

    h = client.patch(
        f"/api/reports/{rid}",
        json={
            "status": "resolved",
            "handle_note": "已删除相关题目",
            "dispose_action": "none",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert h.status_code == 200, h.text
    assert h.json()["status"] == "resolved"

    tracked = client.get("/api/reports/track/" + no).json()
    assert tracked["status"] == "resolved"
    assert tracked["status_label"] == "已处置"
    assert "已删除相关题目" in tracked["handle_note"]

    summary = client.get(
        "/api/reports/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert summary.status_code == 200
    assert summary.json()["counts"]["total"] >= 1


def test_dispose_disable_account_actually_disables(client):
    """处置动作 disable_account：账号真停用，其会话被注销"""
    admin_name = "adm2_" + uuid.uuid4().hex[:8]
    _mk_user(admin_name, admin=True)
    token = _token(client, admin_name)

    victim = "victim_" + uuid.uuid4().hex[:8]
    victim_id = _mk_user(victim, admin=False)
    vtoken = _token(client, victim)

    r = _submit(
        client,
        ip="198.51.100.8",
        target_type="user",
        target_id=victim_id,
        detail="这个账号在发布违法有害信息",
    )
    no = r.json()["report_no"]
    listing = client.get("/api/reports", headers={"Authorization": f"Bearer {token}"})
    rid = [x for x in listing.json() if x["report_no"] == no][0]["id"]

    h = client.patch(
        f"/api/reports/{rid}",
        json={
            "status": "resolved",
            "handle_note": "核实后停用",
            "dispose_action": "disable_account",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert h.status_code == 200, h.text
    assert h.json()["dispose_action"] == "disable_account"
    assert "停用" in h.json()["handle_note"]

    with Session(engine) as s:
        row = s.get(User, victim_id)
        assert row is not None
        assert row.is_active is False, "账号应已停用"
        sessions = s.exec(
            select(Session_).where(Session_.user_id == victim_id)
        ).all()
        assert len(sessions) == 0, "该账号的会话应全部失效"

    # 停用后旧 token 立刻失效
    after = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {vtoken}"}
    )
    assert after.status_code in (401, 403), after.text


# ============ 5. 限流 ============


def test_rate_limit_per_ip(client):
    """同一 IP 一小时内超过上限 → 429

    ⚠️ IP 必须**每次运行都不同** —— 限流是按「IP + 最近一小时」算的，
    而测试库是开发库（不是每次都清空的），上一轮跑剩的记录还在。
    用固定 IP 的话，第二轮跑时第一条就会被上一轮的残留顶掉 → 429，
    用例就成了「测上一轮的垃圾」而不是「测本轮的限流」。
    """
    # 203.0.113.0/24 是文档专用网段，随便用；后两位取随机数保证每轮不同
    ip = "203.0.113.%d" % (uuid.uuid4().int % 254)
    codes = []
    for _ in range(21):
        codes.append(_submit(client, ip=ip).status_code)
    assert codes[:20] == [200] * 20, "前 20 条应受理：%r" % codes[:20]
    assert codes[20] == 429, "第 21 条应被限流拒绝：%r" % codes[20]


def test_clean_text_strips_zero_width():
    """入库前剥掉零宽字符与控制字符"""
    from app.services.reports import clean_text

    dirty = "违\u200b法\u200b内容\n\t"
    assert clean_text(dirty, 100) == "违法内容"
