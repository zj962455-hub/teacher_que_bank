"""几何示意图裁剪 —— OCR 读不懂图，但图还在像素里

背景
----
灰度实测里最典型的一张：文字全对，三角形没了。
OCR 只输出文字，几何图形元素（三角形、垂足、辅助线、圆）一个也读不出来。
题库里虽然存着原图路径，可导出试卷时那张图被扔了 ——
学生的卷子上只剩一段没有图的证明题，这道题就废了。

这里做的事：把图从原图里**裁出来单独存一份**。

怎么找到图
----------
1. OCR 给了每个文本块的 bbox —— 那就是「文字区」
2. 把文字区从图上抹掉
3. 剩下的墨迹做连通块（游程 + 并查集），再按三条判据筛「线」
4. 挨得近的线聚成一簇 —— 那簇就是一个几何图
5. 裁出来，单独存一份 PNG

三条判据（都是被真实样本逼出来的）
----------------------------------
- **够长**：长度 >= 1.8 倍字符高 —— 单个汉字才 1 倍字符高，直接出局
- **每行段数少**：一行里最多只能有 6 段墨迹
  —— 一行汉字是 20 多个独立字块（段），一张图是 1~5 条线穿过（段）
- **够空**：墨迹面积占包围盒的比例 <= 0.4
  —— 实心黑块（照片、阴影）会被这一条挡掉

宁可漏，不可错
--------------
拿不准就返回 None —— 题目里就没图，
但绝不会把一段没认出来的字当成图贴到卷子上。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# 灰度阈值：小于它算「有墨」
INK_LEVEL = 200

# 线段筛选（相对字符高度自适应，字符高取 OCR 文本框高度的中位数）
MIN_LINE_FACTOR = 1.8      # 线的长度 >= 1.8 倍字符高
MIN_CLUSTER_LINES = 1       # 三角形三条边是**连通的**，一个连通块就够
CLUSTER_GAP_FACTOR = 1.2   # 线的间隔 <= 1.2 倍字符高算同一张图
MIN_CLUSTER_W_FACTOR = 2.0  # 图的宽度 >= 2 倍字符高
MIN_CLUSTER_H_FACTOR = 1.5  # 图的高度 >= 1.5 倍字符高（一行文字只有 1 倍）
MAX_ROWS_RUNS_FACTOR = 0.5  # 一行里最多 char_h/2 段墨迹（汉字一行 20+ 段）
MIN_ROWS_RUNS = 6
MAX_DENSITY = 0.4           # 墨迹面积 / 包围盒面积 —— 实心块出局
PAD_FACTOR = 0.2            # 裁图留边
FRAME_RATIO = 0.9           # 长度接近整幅的线当成边框/分割线，不要


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _text_boxes(blocks: list[dict] | None) -> list[tuple[float, float, float, float]]:
    """从 OCR 块里取出文字区的 bbox"""
    boxes: list[tuple[float, float, float, float]] = []
    for block in blocks or []:
        if not isinstance(block, dict) or block.get("type") == "table":
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox[:4])
        except (TypeError, ValueError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        boxes.append((x1, y1, x2, y2))
    return boxes


def _is_text_block(box: tuple[float, float, float, float], char_h: float) -> bool:
    """这个 bbox 是「一行文字」还是「顶点字母标注」？

    为什么要分清
    ------------
    OCR 会把图上的 A/B/C/D 标注也当成文字返回。它们的框很小，
    但正好压在几何线条上 —— 抹掉这些框会把线**切断**，
    裁出来的图就少了半条线（实测样本 B 的底边就是这么断的）。

    判据：整行文字又宽又扁（宽度 >= 1.6 倍字符高），标注字母则是小方块。
    """
    w = box[2] - box[0]
    h = box[3] - box[1]
    if h >= 1.2 * char_h:
        return True            # 高个子 —— 整行文字或竖排公式
    if w >= 1.6 * char_h and h >= 0.5 * char_h:
        return True            # 宽而扁 —— 整行文字
    return False               # 小方块 —— 顶点字母标注，别挡


def detect_figure_bbox(
    image_path: str | Path,
    blocks: list[dict] | None = None,
) -> Optional[tuple[int, int, int, int]]:
    """找出图里几何示意图的位置；找不到返回 None

    返回 (x1, y1, x2, y2)，坐标是原图像素。
    """
    from PIL import Image, ImageChops, ImageDraw

    path = Path(image_path)
    if not path.is_file():
        return None

    with Image.open(path) as im:
        gray = im.convert("L")
        width, height = gray.size
        if width < 40 or height < 40:
            return None

        all_boxes = _text_boxes(blocks)
        char_h = _median([b[3] - b[1] for b in all_boxes]) or (height / 18.0)
        # 只抹「整行文字」—— 顶点字母的小方块留着，否则会把几何线切断
        boxes = [b for b in all_boxes if _is_text_block(b, char_h)]

        # 1) 墨迹二值化
        binary = gray.point(lambda v: 255 if v < INK_LEVEL else 0)
        # 2) 文字区抹掉（OCR 的 bbox 就是文字区）
        mask = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(mask)
        for x1, y1, x2, y2 in boxes:
            draw.rectangle([x1, y1, x2, y2], fill=0)
        ink = ImageChops.darker(binary, mask)
        data = ink.tobytes()

        min_len = max(16.0, char_h * MIN_LINE_FACTOR)
        max_rows_runs = max(MIN_ROWS_RUNS, int(char_h * MAX_ROWS_RUNS_FACTOR))
        gap_limit = max(8.0, char_h * CLUSTER_GAP_FACTOR)
        max_extent = max(width, height) * FRAME_RATIO

        # 3) 逐行取墨段，用并查集合并成连通块（游程法）
        parent: list[int] = []
        runs: list[list[int]] = []      # [x1, y1, x2, y2, 面积]

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        prev_runs: list[tuple[int, int, int]] = []
        for y in range(height):
            row = data[y * width:(y + 1) * width]
            if 255 not in row:
                prev_runs = []
                continue
            cur_runs: list[tuple[int, int, int]] = []
            pos = 0
            while True:
                start = row.find(255, pos)
                if start == -1:
                    break
                end = row.find(0, start)
                if end == -1:
                    end = width
                idx = len(runs)
                parent.append(idx)
                runs.append([start, y, end, y, end - start])
                cur_runs.append((start, end, idx))
                pos = end + 1

            for x1, x2, idx in cur_runs:
                for px1, px2, pidx in prev_runs:
                    if px1 - 1 <= x2 and x1 - 1 <= px2:
                        union(idx, pidx)
            prev_runs = cur_runs

        # 4) 聚合每个连通块：包围盒 + 墨迹面积 + 每行的段数
        stats: dict[int, list] = {}
        row_runs: dict[int, dict[int, int]] = {}
        for i, (x1, y1, x2, y2, area) in enumerate(runs):
            root = find(i)
            box = stats.get(root)
            if box is None:
                box = [x1, y1, x2, y2, 0]
                stats[root] = box
                row_runs[root] = {}
            box[0] = min(box[0], x1)
            box[1] = min(box[1], y1)
            box[2] = max(box[2], x2)
            box[3] = max(box[3], y2)
            box[4] += area
            rows = row_runs[root]
            rows[y1] = rows.get(y1, 0) + 1

        # 5) 筛「线」：够长 + 每行段数少 + 不实心
        lines: list[tuple[int, int, int, int, int]] = []
        for root, box in stats.items():
            x1, y1, x2, y2, area = box
            extent = max(x2 - x1, y2 - y1)
            if extent < min_len or extent >= max_extent:
                continue
            rows = row_runs.get(root, {})
            if rows and max(rows.values()) > max_rows_runs:
                continue
            density = area / max(1.0, float((x2 - x1) * (y2 - y1)))
            if density > MAX_DENSITY:
                continue
            lines.append((x1, y1, x2, y2, area))
        if len(lines) < MIN_CLUSTER_LINES:
            return None

        # 6) 挨得近的线聚成一簇
        cparent = list(range(len(lines)))

        def cfind(i: int) -> int:
            while cparent[i] != i:
                cparent[i] = cparent[cparent[i]]
                i = cparent[i]
            return i

        def cunion(a: int, b: int) -> None:
            ra, rb = cfind(a), cfind(b)
            if ra != rb:
                cparent[rb] = ra

        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                ax1, ay1, ax2, ay2, _ = lines[i]
                bx1, by1, bx2, by2, _ = lines[j]
                dx = max(0, max(ax1 - bx2, bx1 - ax2))
                dy = max(0, max(ay1 - by2, by1 - ay2))
                if dx <= gap_limit and dy <= gap_limit:
                    cunion(i, j)

        clusters: dict[int, list[int]] = {}
        for i in range(len(lines)):
            clusters.setdefault(cfind(i), []).append(i)

        best: tuple[int, int, int, int, int] | None = None
        for members in clusters.values():
            if len(members) < MIN_CLUSTER_LINES:
                continue
            x1 = min(lines[m][0] for m in members)
            y1 = min(lines[m][1] for m in members)
            x2 = max(lines[m][2] for m in members)
            y2 = max(lines[m][3] for m in members)
            if (x2 - x1) < char_h * MIN_CLUSTER_W_FACTOR:
                continue
            if (y2 - y1) < char_h * MIN_CLUSTER_H_FACTOR:
                continue
            area = (x2 - x1) * (y2 - y1)
            if best is None or area > best[0]:
                best = (area, x1, y1, x2, y2)
        if best is None:
            return None

        _, x1, y1, x2, y2 = best

        # 7) 把紧挨着的碎块（顶点字母 A/B/C 这类标注）也框进来
        for box in stats.values():
            bx1, by1, bx2, by2, _ = box
            dx = max(0, max(x1 - bx2, bx1 - x2))
            dy = max(0, max(y1 - by2, by1 - y2))
            if dx <= gap_limit and dy <= gap_limit:
                x1 = min(x1, bx1)
                y1 = min(y1, by1)
                x2 = max(x2, bx2)
                y2 = max(y2, by2)

        pad = max(2, int(char_h * PAD_FACTOR))
        return (
            max(0, int(x1) - pad),
            max(0, int(y1) - pad),
            min(width, int(x2) + pad),
            min(height, int(y2) + pad),
        )


def crop_figure_png(
    image_path: str | Path,
    blocks: list[dict] | None = None,
) -> bytes | None:
    """裁出几何示意图，返回 PNG 字节；裁不出来返回 None"""
    import io

    from PIL import Image

    bbox = detect_figure_bbox(image_path, blocks)
    if bbox is None:
        return None

    with Image.open(image_path) as im:
        region = im.crop(bbox)
        buf = io.BytesIO()
        region.save(buf, format="PNG")
        return buf.getvalue()


def crop_bbox_png(
    image_path: str | Path,
    bbox: list[float],
    padding: int = 4,
) -> bytes | None:
    """按给定 bbox 裁图并返回 PNG 字节

    强模型(PP-StructureV3)的版面模型会把图形标成 figure 块并给出 bbox ——
    那是模型直接说的「图在这儿」，比自己猜准得多。
    """
    import io

    from PIL import Image

    path = Path(image_path)
    if not path.is_file() or not bbox or len(bbox) < 4:
        return None

    with Image.open(path) as im:
        width, height = im.size
        x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        x1 = max(0, int(x1) - padding)
        y1 = max(0, int(y1) - padding)
        x2 = min(width, int(x2) + padding)
        y2 = min(height, int(y2) + padding)
        if x2 <= x1 or y2 <= y1:
            return None
        region = im.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        region.save(buf, format="PNG")
        return buf.getvalue()
