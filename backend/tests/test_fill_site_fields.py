# -*- coding: utf-8 -*-
"""备案回填脚本 _set_site_fields.py 的回归测试

为什么要有这个文件
------------------
2026-11-20 发现一个**会静默假成功**的 bug：脚本算出了新的 site.config.js
内容（改了内存里的 s），**却从不把 s 写回磁盘**。于是它照样打印
「已写入 MPS = 浙公网安备XXXX号」，但文件里 MPS 仍是空串。

后果：备案号回填脚本会一路构建 → rsync → 验收，最后打印
「✅ 备案信息已回填并上线」，**而号一个字都没进 site.config.js** ——
构建和验收用的都是空值，等于什么都没做却报告成功。

这个测试盯住两件事：
1. 写入必须真的落盘（bug 的本体）
2. 样例值必须被拒（照抄文档示例就会把假信息推到公网）

跑法：cd backend && ./venv/bin/python3 -m pytest tests/test_fill_site_fields.py -q
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "teacher-bank" / "_set_site_fields.py"

# 真实的假值 —— 必须能通过脚本的样例值校验（不能误伤合法写入）
FAKE_OPERATOR = "测试运营主体"
FAKE_CONTACT = "contact@test.org"


def _sandbox(tmp_path):
    """造一个和仓库同构的目录。

    关键：site.config.js 必须在 frontend/src/ 下 —— 脚本据此推导
    .env.local 的位置（frontend/.env.local），目录结构不对会写错地方。
    """
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "frontend" / "src" / "site.config.js", src / "site.config.js")
    (tmp_path / "frontend" / ".env.local").write_text(
        "VITE_OPERATOR=\nVITE_CONTACT=\n", encoding="utf-8"
    )
    return src / "site.config.js"


def _run(cfg, mps="", operator="", contact=""):
    return subprocess.run(
        [sys.executable, str(SCRIPT), mps, operator, contact, str(cfg)],
        capture_output=True,
        text=True,
    )


def test_mps_is_actually_persisted_to_disk(tmp_path):
    """写入必须落盘 —— 只 print 不写文件会让回填静默假成功"""
    cfg = _sandbox(tmp_path)
    r = _run(cfg, mps="浙公网安备12345678901234号")
    assert r.returncode == 0, r.stderr
    text = cfg.read_text(encoding="utf-8")
    assert "export const MPS = '浙公网安备12345678901234号'" in text, (
        "MPS 没有落盘到 site.config.js —— 脚本会打印「已写入」但文件没变，"
        "备案号回填会静默假成功"
    )


def test_operater_and_contact_go_to_env_local_not_repo_file(tmp_path):
    """主体/联系方式写 .env.local（不入库），不能进 site.config.js"""
    cfg = _sandbox(tmp_path)
    r = _run(cfg, operator=FAKE_OPERATOR, contact=FAKE_CONTACT)
    assert r.returncode == 0, r.stderr
    env = (tmp_path / "frontend" / ".env.local").read_text(encoding="utf-8")
    assert "VITE_OPERATOR=" + FAKE_OPERATOR in env
    assert "VITE_CONTACT=" + FAKE_CONTACT in env
    text = cfg.read_text(encoding="utf-8")
    assert FAKE_OPERATOR not in text, "个人信息不该出现在入库文件 site.config.js 里"
    assert FAKE_CONTACT not in text


def test_sample_values_are_rejected(tmp_path):
    """样例值必须被拒 —— 照抄文档示例就等于把假信息推到公网"""
    for bad in ("某某公司", "待填", "13800000000", "13800138000", "公司全称"):
        cfg = _sandbox(tmp_path)
        r = _run(cfg, operator=bad)
        assert r.returncode != 0, "样例值 %r 竟然被接受了" % bad
        assert "拒绝" in (r.stdout + r.stderr)


def test_angle_bracket_placeholders_are_rejected(tmp_path):
    """尖括号写法 = 没填的占位，必须被拒"""
    cfg = _sandbox(tmp_path)
    r = _run(cfg, contact="<对外联系方式>")
    assert r.returncode != 0
    assert "拒绝" in (r.stdout + r.stderr)


def test_empty_value_means_no_change(tmp_path):
    """空值 = 这一项不动（不是清空）—— 防止把 .env.local 里的真值擦掉"""
    cfg = _sandbox(tmp_path)
    env = tmp_path / "frontend" / ".env.local"
    env.write_text("VITE_OPERATOR=已填好的值\nVITE_CONTACT=另一个值\n", encoding="utf-8")
    before = env.read_text(encoding="utf-8")
    r = _run(cfg, mps="浙公网安备12345678901234号")
    assert r.returncode == 0, r.stderr
    assert env.read_text(encoding="utf-8") == before, "空值不该改动 .env.local"


def test_rejected_value_leaves_files_untouched(tmp_path):
    """被拒时不能有半成品落盘"""
    cfg = _sandbox(tmp_path)
    env = tmp_path / "frontend" / ".env.local"
    before_cfg = cfg.read_text(encoding="utf-8")
    before_env = env.read_text(encoding="utf-8")
    r = _run(cfg, operator="某某公司")
    assert r.returncode != 0
    assert cfg.read_text(encoding="utf-8") == before_cfg
    assert env.read_text(encoding="utf-8") == before_env
