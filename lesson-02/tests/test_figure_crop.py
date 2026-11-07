"""figure_crop 的单测

跑法：
    python3 -m pytest lesson-02/tests/test_figure_crop.py -q
    python3 lesson-02/tests/test_figure_crop.py      # 没装 pytest 也能跑
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.figure_crop import crop_figure_png, detect_figure_bbox  # noqa: E402


def _make_image(tmp_path: Path, with_triangle: bool):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (500, 300), "white")
    draw = ImageDraw.Draw(img)
    # 一行字（模拟题干）
    draw.text((12, 12), "1. As shown, in triangle ABC, AB = AC", fill="black")
    blocks = [{"type": "text", "text": "1. As shown", "bbox": [5, 5, 260, 30]}]

    if with_triangle:
        # 右上角画一个三角形（几何图的特征：长而薄的线）
        draw.line([(360, 70), (455, 215)], fill="black", width=3)
        draw.line([(455, 215), (305, 215)], fill="black", width=3)
        draw.line([(305, 215), (360, 70)], fill="black", width=3)
        # 顶点旁的标注字母
        draw.text((352, 52), "A", fill="black")
        draw.text((292, 218), "B", fill="black")
        draw.text((458, 218), "C", fill="black")

    path = tmp_path / "sample.png"
    img.save(path)
    return path, blocks


def test_detects_triangle(tmp_path):
    path, blocks = _make_image(tmp_path, with_triangle=True)
    bbox = detect_figure_bbox(path, blocks)
    assert bbox is not None, "三角形应该被识别出来"
    x1, y1, x2, y2 = bbox
    assert x2 > 300 and x1 < 460, f"bbox 应覆盖三角形区域，实际 {bbox}"
    assert y1 < 100 and y2 > 200, f"bbox 应覆盖三角形区域，实际 {bbox}"


def test_text_only_has_no_figure(tmp_path):
    path, blocks = _make_image(tmp_path, with_triangle=False)
    assert detect_figure_bbox(path, blocks) is None


def test_missing_file_returns_none(tmp_path):
    assert detect_figure_bbox(tmp_path / "nope.png", []) is None


def test_crop_returns_png_bytes(tmp_path):
    path, blocks = _make_image(tmp_path, with_triangle=True)
    png = crop_figure_png(path, blocks)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                fn(Path(tmp))
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {name}: {exc}")
    print("FAILED" if failures else "ALL PASSED")
    sys.exit(1 if failures else 0)
