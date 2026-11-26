#!/usr/bin/env python3
"""渲染 lanhu-lab.top（一级域名）静态首页。

为什么需要渲染而不是直接用静态文件
------------------------------------
备案要公示的信息分散在两个地方：
  · frontend/src/site.config.js  -> SITE_NAME / ICP / MPS
  · frontend/.env.local          -> VITE_OPERATOR / VITE_CONTACT（真实值，不入库）

首页必须和题库站显示同一套备案信息（站名、ICP 号、公安备案号），
所以这里从同一个源渲染，避免两处各写一份、改一处忘一处。

渲染产物含真实姓名/邮箱（个保法第 17 条要求公示），**只放服务器**，
不入 git —— 构建输出默认在 /tmp，不在仓库目录里。

用法:
    python3 render.py [输出目录]      # 默认 /tmp/lanhu-home-build
"""

import html
import pathlib
import re
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
TEMPLATE = pathlib.Path(__file__).resolve().parent / "index.html.template"

MIIT_URL = "https://beian.miit.gov.cn/"
MPS_QUERY = "https://beian.mps.gov.cn/#/query/webSearch?code="
REPORT_12377 = "https://www.12377.cn/"
REPORT_POLICE = "https://cyberpolice.mps.gov.cn"

# 二级域名（题库站）—— 一级域名只做门户，指向它
SUBDOMAIN = "tqb.lanhu-lab.top"


def read_site_config():
    """从 site.config.js 取 SITE_NAME / ICP / MPS。

    用正则而不是 import：site.config.js 里有 import.meta.env，
    Node 之外没法直接 import（而 .env.local 的真实值只在 Vite 构建时注入）。
    """
    txt = (FRONTEND / "src" / "site.config.js").read_text(encoding="utf-8")

    def grab(name, default=""):
        m = re.search(r"export const %s\s*=\s*'([^']*)'" % name, txt)
        return m.group(1) if m else default

    return grab("SITE_NAME", "蓝狐网"), grab("ICP"), grab("MPS")


def read_env_local():
    """读 frontend/.env.local 里的 VITE_OPERATOR / VITE_CONTACT。

    真值只存在本机（.gitignore 已忽略），仓库里的 .env.production 是空值占位。
    """
    vals = {}
    p = FRONTEND / ".env.local"
    if not p.exists():
        return vals
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def build_mps_block(mps):
    """公安备案号块。

    号还没下发 -> 返回空串（整块不渲染，不显示半截空号）。
    号下发后 -> 显示图标 + 全称，链接 code 参数只放数字
    （公安官网自己的示例就是 ?code=11010102000001，显示文字才是全称）。
    """
    if not mps:
        return ""
    code = re.search(r"\d{6,}", mps)
    href = MPS_QUERY + (code.group(0) if code else "")
    return (
        '<a class="mps" href="%s" target="_blank" rel="noopener noreferrer">'
        '<img class="mps-icon" src="/gh-beian.png" alt="公安备案图标" />%s</a>'
        % (html.escape(href, quote=True), html.escape(mps))
    )


def main():
    out_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/lanhu-home-build")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    site_name, icp, mps = read_site_config()
    env = read_env_local()
    operator = env.get("VITE_OPERATOR", "")
    contact = env.get("VITE_CONTACT", "")

    if not site_name or not icp:
        raise SystemExit("site.config.js 里 SITE_NAME / ICP 取不到 —— 停止渲染，别上线半成品页")

    page = TEMPLATE.read_text(encoding="utf-8")
    mapping = {
        "{{SITE_NAME}}": html.escape(site_name),
        "{{ICP}}": html.escape(icp),
        "{{MPS_BLOCK}}": build_mps_block(mps),
        "{{OPERATOR}}": html.escape(operator) if operator else "见隐私政策页",
        "{{CONTACT}}": html.escape(contact) if contact else "见隐私政策页",
        "{{APP_URL}}": "https://%s/" % SUBDOMAIN,
        "{{PRIVACY_URL}}": "https://%s/privacy" % SUBDOMAIN,
        "{{GUIDE_URL}}": "https://%s/guide" % SUBDOMAIN,
        "{{MIIT_URL}}": MIIT_URL,
        "{{REPORT_12377}}": REPORT_12377,
        "{{REPORT_POLICE}}": REPORT_POLICE,
    }
    for k, v in mapping.items():
        page = page.replace(k, v)

    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", page)
    if left:
        raise SystemExit("模板还有没替换的占位符: %s" % sorted(set(left)))

    (out_dir / "index.html").write_text(page, encoding="utf-8")

    # 图标资产：从题库前端 public/ 复制，避免外链（公安图标外链已失效过一次）
    pub = FRONTEND / "public"
    for name in ("gh-beian.png", "favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        src = pub / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    print("rendered -> %s" % out_dir)
    print("  site=%s icp=%s mps=%s" % (site_name, icp, mps or "(未下发,不渲染)"))
    print("  operator=%s contact=%s" % ("已填" if operator else "空", "已填" if contact else "空"))


if __name__ == "__main__":
    main()
