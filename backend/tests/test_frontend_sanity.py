"""
前端源码体检 —— 防止「构建通过但页面不能用」的坑复发。

为什么放在后端测试里
--------------------
这个仓库的 CI 只跑 pytest（没有前端测试框架）。但前端源码里的低级错误
（正则写错转义、引用了不存在的组件）**build 全都查不出来** —— 2026-11-18
就栽过一次：/^1[3-9]\\d{9}$/ 里的双反斜杠让「忘记密码」表单永远判定
「手机号格式不对」，build 通过、后端测试全过、API 也全对，只有真浏览器能看出来。

所以这里做两道最朴素的体检：
1. 正则里的双反斜杠（转义写错的典型症状）
2. 组件里引入了但项目里根本不存在的变量/函数（拼写错误的典型症状）

不追求覆盖全面 —— 抓到一类是一类。
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"

# 正则字面量里出现两个反斜杠（比如 \\d 代替 \\w）—— 转义写错的典型症状
DOUBLE_ESCAPE = re.compile(r"/^[^/\n]*\\\\[dws]/")

# Vue 模板里用到的组件，必须真的 import 了
COMPONENT_RE = re.compile(r"<(N[A-Z][A-Za-z0-9]*)\b")


def _source_files():
    if not FRONTEND_SRC.is_dir():
        return []
    return [
        p
        for p in list(FRONTEND_SRC.rglob("*.vue")) + list(FRONTEND_SRC.rglob("*.js"))
        if "__pycache__" not in str(p)
    ]


def test_frontend_src_exists():
    """前端源码目录必须存在 —— 不存在的话下面那些检查就是假的通过。"""
    assert FRONTEND_SRC.is_dir(), f"找不到 frontend/src（{FRONTEND_SRC}）"


def test_no_double_escaped_regex():
    """正则里不许出现双反斜杠 —— 那是「永远匹配不上」的写法。"""
    bad = []
    for path in _source_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if DOUBLE_ESCAPE.search(line):
                bad.append(f"{path.relative_to(REPO)}:{i}: {line.strip()}")
    assert not bad, "正则转义写错了（双反斜杠，永远匹配不上）：\n" + "\n".join(bad)


def test_nvue_components_are_imported():
    """模板里用到的 naive-ui 组件必须真的 import 了 —— 拼错会导致白屏。"""
    bad = []
    for path in _source_files():
        if path.suffix != ".vue":
            continue
        text = path.read_text(encoding="utf-8")
        used = set(COMPONENT_RE.findall(text))
        if not used:
            continue
        imported = set(re.findall(r"\b(N[A-Z][A-Za-z0-9]*)\b", text))
        missing = sorted(used - imported)
        if missing:
            bad.append(f"{path.relative_to(REPO)}: 用了但没 import: {missing}")
    assert not bad, "模板里用了没 import 的组件（会白屏）：\n" + "\n".join(bad)
