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

def test_mps_icon_is_hosted_locally():
    """公安备案图标必须本地托管 —— 官方外链已经死了。

    踩过的坑（2026-11-18）：官方老路径 https://beian.mps.gov.cn/img/gh.png
    返回的是官网 SPA 的 index.html（content-type: text/html，749 字节），
    浏览器会把它当 HTML 解析 → 页脚图标位置变成空白/裂图。
    现在用的是官网真图（金色公安徽章），已下载到 frontend/public/gh-beian.png。

    这里保证：① 文件在；② 源码里不再引用那个死链。
    """
    icon = REPO / "frontend" / "public" / "gh-beian.png"
    assert icon.is_file(), "公安备案图标丢了：frontend/public/gh-beian.png"

    dead = "beian.mps.gov.cn/img/gh.png"
    hits = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        # 先剥掉注释 —— 说明性注释里提到这个死链是正常的
        #（那段注释恰恰就是在记录「这链接已失效」，不该误伤）
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"[/][*].*?[*]/", "", text, flags=re.S)
        text = re.sub(r"(?m)^[ ]*//.*$", "", text)
        if dead in text:
            hits.append(str(path.relative_to(REPO)))
    assert not hits, "又在引用已失效的官方外链图标（%s），改用本地 gh-beian.png" % dead


def test_mps_link_uses_digit_only_code():
    """公安备案链接的 code 参数只放数字，不能把「浙公网安备…号」全称塞进去。

    依据：公安官网自己页面里硬编码的示例是
      https://beian.mps.gov.cn/#/query/webSearch?code=11010102000001
    显示文字才是「京公网安备11010102000001号」。
    所以链接参数用数字、显示用全称。
    """
    # lesson-43：备案字段收口到 site.config.js —— 页脚从这里 import
    config = REPO / "frontend" / "src" / "site.config.js"
    assert config.is_file(), "缺少 frontend/src/site.config.js（备案字段的唯一来源）"
    ctext = config.read_text(encoding="utf-8")
    footer = REPO / "frontend" / "src" / "components" / "SiteFooter.vue"
    text = footer.read_text(encoding="utf-8")
    assert "MPS_CODE" in text, "页脚没有用 MPS_CODE（code 参数应只放数字）"
    assert "MPS.match(" in ctext, "MPS_CODE 应从全称里自动摘出数字，别手填两份"

def test_no_mustache_inside_static_attribute():
    """静态属性里不许出现 {{ }} 插值 —— 那是「原样输出成字面量」的写法。

    踩过的坑（2026-11-18）：页脚的公安备案链接写成
    href="https://beian.mps.gov.cn/#/query/webSearch?code={{ MPS }}"
    Vue 的插值在属性里不生效，会原样输出 —— 等到真填上备案号才发现链接是废的。
    这里提前拦住。

    只扫 <template> 段，并先剥掉 HTML 注释 ——
    注释里写反例是正常写法，不该误伤（第一版就误伤了自己写的注释）。
    """
    bad = []
    attr_re = re.compile(r'(:|@|v-bind:)?([a-zA-Z][a-zA-Z0-9:_-]*)="([^"]*)"')
    for path in _source_files():
        if path.suffix != ".vue":
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        m = re.search(r"<template[^>]*>(.*)</template>", text, flags=re.S)
        scope = m.group(1) if m else text
        for line in scope.splitlines():
            for prefix, name, value in attr_re.findall(line):
                if prefix:
                    continue
                if "{{" in value:
                    bad.append("%s: %s=%r" % (path.relative_to(REPO), name, value))
    assert not bad, "静态属性里 wrote {{ }} 插值（会原样输出成字面量）：" + chr(10) + chr(10).join(bad)
