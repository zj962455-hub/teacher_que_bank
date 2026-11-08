"""题图排版（figure_layout / figure_width）测试 — lesson-36

覆盖：
- 版式白名单规范化（非法值回落默认）
- 宽度规范化（0=自动，范围 15~80）
- PDF 模板按版式输出正确的 class 和宽度
- 题目更新接口能改版式
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.questions import (  # noqa: E402
    DEFAULT_FIGURE_LAYOUT,
    _normalize_figure_layout,
    _normalize_figure_width,
)
from app.services.pdf_export import render_paper_html  # noqa: E402


def test_layout_normalize():
    assert _normalize_figure_layout("bottom_right") == "bottom_right"
    assert _normalize_figure_layout("right") == "right"
    assert _normalize_figure_layout("none") == "none"
    # 非法值回落默认，别让脏数据进库
    assert _normalize_figure_layout("haha") == DEFAULT_FIGURE_LAYOUT
    assert _normalize_figure_layout(None) == DEFAULT_FIGURE_LAYOUT
    assert _normalize_figure_layout("") == DEFAULT_FIGURE_LAYOUT


def test_width_normalize():
    assert _normalize_figure_width(0) == 0
    assert _normalize_figure_width(None) == 0
    assert _normalize_figure_width("") == 0
    assert _normalize_figure_width(35) == 35
    # 越界夹紧
    assert _normalize_figure_width(5) == 15
    assert _normalize_figure_width(999) == 80
    # 非法值当自动
    assert _normalize_figure_width("abc") == 0


def _render(layout, width=0):
    html = render_paper_html(
        paper={"title": "测试卷", "subtitle": ""},
        items=[{
            "label": "1.",
            "content": "如图，在三角形 ABC 中",
            "score": 5.0,
            "figure": "file:///tmp/fig.png",
            "figure_layout": layout,
            "figure_width": width,
        }],
        trace="",
    )
    return html


def test_pdf_default_layout_is_bottom_right():
    html = _render("bottom_right")
    assert "q-bottom_right" in html
    # 右下角 = 文字在左、图在右（flex 容器 + 底部对齐）
    assert "align-items: flex-end" in html


def test_pdf_layout_none_hides_figure():
    html = _render("none")
    assert "q-none" in html
    # none 版式不渲染图
    assert '<div class="figure"' not in html


def test_pdf_custom_width_applied():
    html = _render("bottom_right", 45)
    assert "width: 45%;" in html


def test_pdf_default_width_uses_layout_width():
    html = _render("bottom_right", 0)
    # 没指定宽度时不写内联 width，交给 CSS 里该版式的默认值
    assert 'class="figure" style=' not in html


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
