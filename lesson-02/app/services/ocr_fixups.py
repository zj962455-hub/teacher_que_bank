"""OCR 结果修复层 —— 数学符号误识别 + 竖式分数重建

背景（2026-11-07 灰度实测）
--------------------------
老师上传的几何题截图，PP-OCR（mobile rec）把常见数学符号认错：

  ∠A+∠B=∠C   ->  ZA+ZB=ZC
  ∠AOB=30°    ->  ZAOB=30° / LAOB=30°
  BQ⊥AD于点Q  ->  BQIAD于点Q
  DE⊥AB       ->  DELAB / DEIAB / DE1AB
  ∠C=60°      ->  ZC=6O°

纠错规则（只在「像数学文本」时生效，避免误伤英文单词里的 Z / I / O）：

1. Z / 7 + 顶点字母(A~E) 开头的串 -> ∠      （ZAOB -> ∠AOB）
2. 行首 L + 三个以上大写字母                -> ∠      （LAOB -> ∠AOB）
3. 大写字母中间夹 I / l / 1                  -> ⊥      （BQIAD -> BQ⊥AD）
4. 数字后紧跟的 O                            -> 0      （6O° -> 60°）

另外提供竖式分数重建：分辨率低时 1/2 会被识别成两个独立小块
（分子在上、分母在下），靠 bbox 几何能拼回一个分数公式块。

修不了的：识别模型整个丢掉的符号（例如 ∠ 消失只剩 A=B=3C），
那种只能靠换更强的识别模型，见 docs/lesson-35-ocr-upgrade.md。
"""

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_UPPER_RUN_RE = re.compile(r"[A-Z]{2,}")
_MATH_MARKERS = ("=", "+", "-", "°", "×", "÷", "△", "∠", "⊥", "%", "√", "≤", "≥", "≠")

# Z / 7 + 顶点字母开头的串 -> ∠
_ANGLE_Z_RE = re.compile(r"(?<![A-Za-z0-9])[Z7](?=[A-E][A-Z]*)")

# 行首 L + 三个以上大写字母 -> ∠
_ANGLE_L_RE = re.compile(r"(?<![A-Za-z0-9])L(?=[A-E][A-Z]{2,})")

# 大写字母中间的 I / l / 1 -> ⊥
_PERP_RE = re.compile(r"(?<=[A-Z])[IlL1](?=[A-Z]{2})")

# 数字后紧跟的 O -> 0
_ZERO_RE = re.compile(r"(?<=\d)O(?=[\d°])")

# 分数的分子/分母：1~3 位数字
_NUM_RE = re.compile(r"^[0-9]{1,3}$")


def looks_like_math(text: str) -> bool:
    """文本像不像数学内容 —— 决定要不要上纠错规则"""
    if not text:
        return False
    if any(m in text for m in _MATH_MARKERS):
        return True
    if not _CJK_RE.search(text):
        return False
    runs = _UPPER_RUN_RE.findall(text)
    return any(len(r) >= 2 for r in runs)


def fix_math_symbols(text: str) -> str:
    """修正 OCR 常见数学符号误识别

    >>> fix_math_symbols("①ZA+ZB=ZC")
    '①∠A+∠B=∠C'
    >>> fix_math_symbols("BQIAD于点Q.")
    'BQ⊥AD于点Q.'
    """
    if not text or not looks_like_math(text):
        return text
    out = _ANGLE_Z_RE.sub("∠", text)
    out = _ANGLE_L_RE.sub("∠", out)
    out = _PERP_RE.sub("⊥", out)
    out = _ZERO_RE.sub("0", out)
    return out


def _bbox(b: dict) -> list:
    bb = b.get("bbox")
    return list(bb) if isinstance(bb, (list, tuple)) and len(bb) >= 4 else []


def _h(b: dict) -> float:
    bb = _bbox(b)
    return (bb[3] - bb[1]) if bb else 0.0


def _w(b: dict) -> float:
    bb = _bbox(b)
    return (bb[2] - bb[0]) if bb else 0.0


def _cx(b: dict) -> float:
    bb = _bbox(b)
    return (bb[0] + bb[2]) / 2 if bb else 0.0


def _conf(b: dict) -> float:
    try:
        return float(b.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def rebuild_fractions(blocks: list) -> list:
    """竖式分数重建：分子块 + 分母块 -> 一个公式块

    实测（2026-11-07）：分辨率低时 1/2 被识别成两个独立小块，
    分子在上、分母在下，靠 bbox 几何（上下排列、水平居中、字号偏小）
    能拼回一个分数。

    只在「两个小块都是 1~3 位数字 + 几何关系成立」时才合并，
    宁可不合并，也不要把两个并列数字错拼成分数。
    """
    if not isinstance(blocks, list) or len(blocks) < 2:
        return blocks

    heights = sorted(
        h for h in (_h(b) for b in blocks
                    if isinstance(b, dict) and isinstance(b.get("text"), str))
        if h > 0
    )
    if not heights:
        return blocks
    median = heights[len(heights) // 2]
    small = 0.75 * median

    cands = []
    for idx, b in enumerate(blocks):
        if not isinstance(b, dict) or b.get("type") != "text":
            continue
        t = (b.get("text") or "").strip()
        if not t or not _NUM_RE.match(t):
            continue
        if not (0 < _h(b) <= small):
            continue
        if not _bbox(b):
            continue
        cands.append(idx)

    merged = {}
    drop = set()
    for a in range(len(cands)):
        i = cands[a]
        if i in merged or i in drop:
            continue
        for b2 in range(a + 1, len(cands)):
            j = cands[b2]
            if j in merged or j in drop:
                continue
            bi, bj = _bbox(blocks[i]), _bbox(blocks[j])
            # 谁在上谁在下，按 bbox y 决定（不依赖 OCR 返回顺序）
            if bi[1] <= bj[1]:
                top, bot = blocks[i], blocks[j]
            else:
                top, bot = blocks[j], blocks[i]
            bt, bb_ = _bbox(top), _bbox(bot)
            gap = bb_[1] - bt[3]
            if gap < -2:
                continue
            if abs(_cx(top) - _cx(bot)) > 0.6 * max(_w(top), _w(bot)):
                continue
            if gap > 0.8 * median:
                continue
            merged[i] = (j, top, bot)
            drop.add(j)
            break

    if not merged:
        return blocks

    out = []
    for idx, blk in enumerate(blocks):
        if idx in drop:
            continue
        if idx not in merged:
            out.append(blk)
            continue
        j, top, bot = merged[idx]
        num = (top.get("text") or "").strip()
        den = (bot.get("text") or "").strip()
        bt, bb_ = _bbox(top), _bbox(bot)
        out.append({
            "type": "formula",
            "latex": "\\frac{%s}{%s}" % (num, den),
            "plain": "%s/%s" % (num, den),
            "bbox": [min(bt[0], bb_[0]), min(bt[1], bb_[1]),
                     max(bt[2], bb_[2]), max(bt[3], bb_[3])],
            "confidence": min(_conf(top), _conf(bot)),
        })
    return out
