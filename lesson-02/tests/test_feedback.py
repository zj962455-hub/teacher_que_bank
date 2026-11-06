"""反馈收集测试 — 课 34

覆盖：
- 提交反馈（落库 + 状态默认 new）
- 内容太短 / 类别不合法 → request.validation_failed
- 普通用户只看得到自己的反馈
- 管理员看得到全部（带提交人用户名）
- 管理员改处理状态
- 普通用户改状态 → 403
- 未登录提交/查看 → 401
- 反馈带「谁提的」（reporter / contact，共享账号下区分老师）
- 汇总统计 / 导出（markdown / csv）—— 仅管理员

跑法：
    cd lesson-02
    venv/bin/python -m pytest tests/test_feedback.py -v
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Feedback, User  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402

PASSWORD = "abc123456"


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清干净数据

    ⚠️ 显式 SQL 按外键顺序删（feedbacks / invites 引用 users）。
    """
    with Session(engine) as session:
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM feedbacks",
            "DELETE FROM invites",
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


# === 辅助 ===

def _make_user(
    username: str,
    *,
    is_admin: bool = False,
    display_name: str = "",
    allow_password_change: bool = True,
) -> int:
    with Session(engine) as session:
        user = User(
            username=username,
            display_name=display_name or username,
            password_hash=hash_password(PASSWORD),
            must_change_password=False,
            is_active=True,
            is_admin=is_admin,
            allow_password_change=allow_password_change,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id or 0


def _login(client, username: str = "test1"):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return resp.json()["token"]


def _h(token: str):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 提交
# ============================================================

def test_submit_feedback(client):
    """提交反馈 → 落库 + 默认状态 new"""
    uid = _make_user("test1")
    token = _login(client)

    resp = client.post(
        "/api/feedback",
        headers=_h(token),
        json={
            "category": "bug",
            "content": "导出 PDF 的时候公式全都变成方块了",
            "page_url": "/papers/12/export",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "bug"
    assert body["content"] == "导出 PDF 的时候公式全都变成方块了"
    assert body["status"] == "new"
    assert body["page_url"] == "/papers/12/export"

    with Session(engine) as session:
        record = session.exec(select(Feedback)).first()
        assert record.user_id == uid
        assert record.status == "new"


def test_submit_feedback_requires_login(client):
    resp = client.post("/api/feedback", json={"category": "bug", "content": "这个功能点不动"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.required"


def test_submit_feedback_content_too_short(client):
    """内容太短 → request.validation_failed"""
    _make_user("test1")
    token = _login(client)
    resp = client.post(
        "/api/feedback",
        headers=_h(token),
        json={"category": "other", "content": "短"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"


def test_submit_feedback_bad_category(client):
    """类别不合法 → request.validation_failed"""
    _make_user("test1")
    token = _login(client)
    resp = client.post(
        "/api/feedback",
        headers=_h(token),
        json={"category": "随手写的", "content": "这个功能点不动"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"


# ============================================================
# 查看
# ============================================================

def test_list_feedback_requires_login(client):
    resp = client.get("/api/feedback")
    assert resp.status_code == 401


def test_normal_user_only_sees_own_feedback(client):
    """普通用户只能看到自己的反馈"""
    _make_user("test1")
    _make_user("test2")
    token1 = _login(client, "test1")
    token2 = _login(client, "test2")

    client.post(
        "/api/feedback",
        headers=_h(token1),
        json={"category": "bug", "content": "test1 提的问题"},
    )
    client.post(
        "/api/feedback",
        headers=_h(token2),
        json={"category": "feature", "content": "test2 提的问题"},
    )

    resp = client.get("/api/feedback", headers=_h(token1))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["content"] == "test1 提的问题"
    # 别人的吐槽一条都看不到
    assert "test2 提的问题" not in resp.text


def test_admin_sees_all_feedbacks(client):
    """管理员看得到全部，且带提交人用户名"""
    _make_user("test1")
    _make_user("boss", is_admin=True)
    token1 = _login(client, "test1")
    token_boss = _login(client, "boss")

    client.post(
        "/api/feedback",
        headers=_h(token1),
        json={"category": "bug", "content": "test1 提的问题"},
    )
    client.post(
        "/api/feedback",
        headers=_h(token_boss),
        json={"category": "other", "content": "管理员自己提的"},
    )

    resp = client.get("/api/feedback", headers=_h(token_boss))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    usernames = {i["username"] for i in body["items"]}
    assert usernames == {"test1", "boss"}


# ============================================================
# 改状态
# ============================================================

def test_admin_can_update_status(client):
    """管理员改处理状态"""
    _make_user("test1")
    _make_user("boss", is_admin=True)
    token1 = _login(client, "test1")
    token_boss = _login(client, "boss")

    created = client.post(
        "/api/feedback",
        headers=_h(token1),
        json={"category": "feature", "content": "希望能批量导出 Word"},
    ).json()

    resp = client.patch(
        f"/api/feedback/{created['id']}",
        headers=_h(token_boss),
        json={"status": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert resp.json()["status_label"] == "已处理"

    with Session(engine) as session:
        record = session.get(Feedback, created["id"])
        assert record.status == "resolved"


def test_normal_user_cannot_update_status(client):
    """普通用户改状态 → 403 auth.forbidden"""
    _make_user("test1")
    token1 = _login(client, "test1")

    created = client.post(
        "/api/feedback",
        headers=_h(token1),
        json={"category": "bug", "content": "这个按钮点不动"},
    ).json()

    resp = client.patch(
        f"/api/feedback/{created['id']}",
        headers=_h(token1),
        json={"status": "resolved"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


def test_update_status_requires_login(client):
    resp = client.patch("/api/feedback/1", json={"status": "read"})
    assert resp.status_code == 401


def test_update_status_invalid_value(client):
    """状态值不合法 → request.validation_failed"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")
    resp = client.patch(
        "/api/feedback/1",
        headers=_h(token),
        json={"status": "随便写的"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"


def test_update_status_missing_feedback_404(client):
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")
    resp = client.patch(
        "/api/feedback/999999",
        headers=_h(token),
        json={"status": "read"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "resource.not_found"


# ============================================================
# 「谁提的」（共享账号下区分老师）
# ============================================================

def test_submit_feedback_with_reporter(client):
    """提交带 reporter + contact → 落库 + 返回"""
    _make_user("test2", display_name="共享账号")
    token = _login(client, "test2")

    resp = client.post(
        "/api/feedback",
        headers=_h(token),
        json={
            "category": "feature",
            "content": "希望能批量导出 Word 文档",
            "reporter": "张老师·市三中",
            "contact": "微信 zhanglaoshi",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reporter"] == "张老师·市三中"
    assert body["contact"] == "微信 zhanglaoshi"

    with Session(engine) as session:
        record = session.exec(select(Feedback)).first()
        assert record.reporter == "张老师·市三中"
        assert record.contact == "微信 zhanglaoshi"


def test_submit_feedback_reporter_fallback_to_display_name(client):
    """reporter 缺省 → 后端用当前用户的 display_name 兜底"""
    _make_user("test2", display_name="李老师·一中")
    token = _login(client, "test2")

    resp = client.post(
        "/api/feedback",
        headers=_h(token),
        json={"category": "bug", "content": "这个按钮点不动"},
    )
    assert resp.status_code == 200
    assert resp.json()["reporter"] == "李老师·一中"

    with Session(engine) as session:
        record = session.exec(select(Feedback)).first()
        assert record.reporter == "李老师·一中"


def test_list_feedbacks_includes_reporter_and_contact(client):
    """列表返回带 reporter / contact（管理员视角）"""
    _make_user("test2", display_name="共享账号")
    _make_user("boss", is_admin=True)
    token = _login(client, "test2")
    token_boss = _login(client, "boss")

    client.post(
        "/api/feedback",
        headers=_h(token),
        json={
            "category": "bug",
            "content": "导出 PDF 的公式全都变成方块了",
            "reporter": "张老师·市三中",
            "contact": "微信 zhanglaoshi",
        },
    )

    resp = client.get("/api/feedback", headers=_h(token_boss))
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["reporter"] == "张老师·市三中"
    assert item["contact"] == "微信 zhanglaoshi"


# ============================================================
# 汇总统计（仅管理员）
# ============================================================

def test_summary_requires_admin(client):
    """未登录 401 / 非管理员 403"""
    resp = client.get("/api/feedback/summary")
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.required"

    _make_user("test1")
    token = _login(client, "test1")
    resp = client.get("/api/feedback/summary", headers=_h(token))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"

    # 导出接口同样仅管理员
    resp = client.get("/api/feedback/export?format=csv", headers=_h(token))
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.forbidden"


def test_summary_counts_and_contributors(client):
    """汇总数字对 + contributors 按提交人聚合（共享账号下区分老师）"""
    _make_user("test2", display_name="共享账号")
    _make_user("boss", is_admin=True)
    token2 = _login(client, "test2")
    token_boss = _login(client, "boss")

    # 两位老师共用 test2 提交
    client.post(
        "/api/feedback",
        headers=_h(token2),
        json={
            "category": "bug",
            "content": "导出 PDF 的时候公式全都变成方块了",
            "reporter": "张老师·市三中",
        },
    )
    client.post(
        "/api/feedback",
        headers=_h(token2),
        json={
            "category": "feature",
            "content": "希望能批量导出 Word 文档",
            "reporter": "张老师·市三中",
        },
    )
    client.post(
        "/api/feedback",
        headers=_h(token2),
        json={"category": "other", "content": "界面上的字太小了", "reporter": "李老师·一中"},
    )

    resp = client.get("/api/feedback/summary", headers=_h(token_boss))
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 3
    assert body["by_category"] == {"bug": 1, "feature": 1, "other": 1}
    assert body["by_status"] == {"new": 3, "read": 0, "resolved": 0}
    assert body["new_count"] == 3
    assert body["resolved_count"] == 0
    assert body["first_at"]
    assert body["last_at"]

    # 共享账号下靠 reporter 区分老师
    counts = {c["reporter"]: c["count"] for c in body["contributors"]}
    assert counts == {"张老师·市三中": 2, "李老师·一中": 1}
    # 每条都带账号信息
    assert all(c["username"] == "test2" for c in body["contributors"])


def test_summary_resolved_count_reflects_status(client):
    """改过状态后，汇总里的已处理数跟着变"""
    _make_user("boss", is_admin=True)
    token_boss = _login(client, "boss")

    created = client.post(
        "/api/feedback",
        headers=_h(token_boss),
        json={"category": "bug", "content": "这个按钮点不动"},
    ).json()
    client.patch(
        f"/api/feedback/{created['id']}",
        headers=_h(token_boss),
        json={"status": "resolved"},
    )

    body = client.get("/api/feedback/summary", headers=_h(token_boss)).json()
    assert body["resolved_count"] == 1
    assert body["new_count"] == 0
    assert body["by_status"]["resolved"] == 1


# ============================================================
# 导出（仅管理员）
# ============================================================

def test_export_csv_escapes_formula_injection(client):
    """CSV 注入防护：= + - @ 开头的单元格前置单引号

    Excel 会把 = 开头的单元格当**公式**执行（=cmd|... 能骗到本地程序）。
    """
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")

    client.post(
        "/api/feedback",
        headers=_h(token),
        json={
            "category": "bug",
            "content": "=cmd|'/c calc'!A1",
            "reporter": "@danger",
            "contact": "+123456",
        },
    )

    resp = client.get("/api/feedback/export?format=csv", headers=_h(token))
    assert resp.status_code == 200
    text = resp.text

    # 被转义了
    assert "'=cmd|'/c calc'!A1" in text
    assert "'@danger" in text
    assert "'+123456" in text
    # 单元格开头没裸露的危险字符
    assert ",=cmd|" not in text
    assert ",@danger" not in text
    assert ",+123456" not in text


def test_export_csv_has_bom(client):
    """CSV 带 BOM —— Excel 打开 UTF-8 中文不乱码"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")
    client.post(
        "/api/feedback",
        headers=_h(token),
        json={"category": "bug", "content": "导出 PDF 的公式全都变成方块了"},
    )

    resp = client.get("/api/feedback/export?format=csv", headers=_h(token))
    assert resp.status_code == 200
    assert resp.text.startswith("\ufeff")
    assert "日期" in resp.text
    assert "提交人" in resp.text


def test_export_markdown_groups_by_category(client):
    """markdown 按类别分组，含日期 / 提交人 / 联系方式 / 状态 / 内容 / 来源页面"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")

    client.post(
        "/api/feedback",
        headers=_h(token),
        json={
            "category": "bug",
            "content": "导出 PDF 的时候公式全都变成方块了",
            "reporter": "张老师·市三中",
            "contact": "微信 zhanglaoshi",
            "page_url": "/papers/12/export",
        },
    )
    client.post(
        "/api/feedback",
        headers=_h(token),
        json={"category": "feature", "content": "希望能批量导出 Word 文档"},
    )

    resp = client.get("/api/feedback/export?format=markdown", headers=_h(token))
    assert resp.status_code == 200
    text = resp.text

    assert "# 老师反馈汇总" in text
    assert "## 功能异常（1 条）" in text
    assert "## 功能建议（1 条）" in text
    assert "张老师·市三中" in text
    assert "微信 zhanglaoshi" in text
    assert "导出 PDF 的时候公式全都变成方块了" in text
    assert "/papers/12/export" in text


def test_export_invalid_format(client):
    """格式不合法 → request.validation_failed"""
    _make_user("boss", is_admin=True)
    token = _login(client, "boss")
    resp = client.get("/api/feedback/export?format=pdf", headers=_h(token))
    assert resp.status_code == 400
    assert resp.json()["code"] == "request.validation_failed"
