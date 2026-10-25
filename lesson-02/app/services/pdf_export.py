"""试卷 PDF 导出 — lesson-09

流程
----
```
题目数据 → Jinja2 渲染 HTML → Playwright(Chromium) 渲染公式 → PDF 文件
```

关键设计：后端不需要 KaTeX 渲染能力
------------------------------------
后端是 Python,没有 KaTeX。但**公式渲染发生在 Chromium 里**：

1. 模板里放的是 markdown 原文(公式是 ``$...$`` 标记)
2. KaTeX 的 auto-render 脚本在浏览器里扫描并替换成公式 HTML
3. Playwright 等 ``window.__katexDone`` 标志,确认渲染完再打印

这样后端只负责"把文字传过去",公式排版交给浏览器引擎 —— 跟前端看到的效果完全一致。

为什么用临时文件 + file:// 而不是 HTTP
--------------------------------------
如果模板里引 ``http://127.0.0.1:8000/static/katex/...``,
Chromium 会反过来请求 FastAPI —— 而生成 PDF 的请求正占着这个服务。
单 worker 时会**死锁**(事件循环被同步的 Playwright 阻塞)。

用 file:// 完全避开这个问题:HTML 临时文件跟 ``static/katex/`` 同级,
相对路径 ``katex/katex.min.css`` 就能正确解析到字体。
"""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# === 路径 ===
APP_DIR = Path(__file__).resolve().parent.parent      # lesson-02/app/
BASE_DIR = APP_DIR.parent                               # lesson-02/
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = APP_DIR / "templates"

# === Jinja2 环境 ===
# autoescape=True → 题干里的 < > & 自动转义,防 XSS
# 公式的 $ 标记不受影响(不是 HTML 特殊字符)
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


class PdfExportError(Exception):
    """PDF 导出失败"""


def render_paper_html(
    paper: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    """把试卷渲染成 HTML 字符串

    Args:
        paper: {"title": ..., "subtitle": ...}
        items: [{"label": "一、", "content": "题干 markdown", "score": 5.0}]
    """
    template = jinja_env.get_template("paper_pdf.html")
    return template.render(paper=paper, items=items)


def export_paper_pdf(
    paper: dict[str, Any],
    items: list[dict[str, Any]],
) -> bytes:
    """生成 PDF,返回二进制内容

    Raises:
        PdfExportError: Playwright 启动失败或渲染超时
    """
    html = render_paper_html(paper, items)

    # === 1. 写临时 HTML ===
    # 放在 static/ 下 → 跟 katex/ 同级,相对路径能解析到
    # 用 uuid 命名避免并发冲突
    tmp_name = f"_pdf_{uuid.uuid4().hex}.html"
    tmp_path = STATIC_DIR / tmp_name

    try:
        tmp_path.write_text(html, encoding="utf-8")

        # === 2. Playwright 渲染 ===
        from playwright.sync_api import sync_playwright

        pdf_bytes = _render_pdf(tmp_path)

        return pdf_bytes

    finally:
        # === 3. 清理临时文件（无论成功失败）===
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _render_pdf(html_path: Path) -> bytes:
    """用 Playwright 把 HTML 转成 PDF"""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            # ⚠️ channel="chromium" 必须写
            # ----------------------------------------------
            # Playwright 1.49+ 的 launch() 在 headless 模式下默认用
            # **chromium_headless_shell**（精简版，~90MB）。
            # 我们只装了完整版 chromium（~400MB），不写这个参数会报
            # "Please run playwright install" —— 明明装过了。
            #
            # 而且 PDF 打印需要完整版的功能（headless_shell 不支持部分 API），
            # 所以指定 channel 是正解，不是绕过。
            browser = p.chromium.launch(
                channel="chromium",
                args=[
                    # 容器/Docker 里常见问题：沙箱需要禁用
                    "--no-sandbox",
                    # 省 /dev/shm（小内存机器必加，ECS 上 /dev/shm 默认只有 64MB）
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                page = browser.new_page()

                # 用 file:// 打开（资源都是本地相对路径）
                page.goto(f"file://{html_path.resolve()}", wait_until="load")

                # 等 KaTeX 渲染完成
                # ⚠️ 模板里 renderMathInElement 之后会设 window.__katexDone
                try:
                    page.wait_for_function(
                        "window.__katexDone === true",
                        timeout=10000,
                    )
                except Exception:
                    # 超时也要继续 —— 至少能出 PDF(公式可能没渲染)
                    pass

                # 打印成 PDF
                # print_background=True → 保留背景色(有些公式需要)
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "18mm",
                        "bottom": "18mm",
                        "left": "16mm",
                        "right": "16mm",
                    },
                )
            finally:
                browser.close()

    except Exception as e:
        raise PdfExportError(f"PDF 渲染失败：{e}") from e

    return pdf_bytes
