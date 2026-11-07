"""本机强模型 OCR 服务（给 teacher-question-bank 调用）

和线上 /opt/paddleocr 的接口契约**完全一致**，可以直接把
PADDLEOCR_BASE_URL 指到本机做对比：

    GET  /api/v1/health
    POST /api/v1/ocr/image   multipart 字段 image，头 X-API-Key
    -> {"ok": true, "blocks": [...], "stats": {...}}

和线上服务的区别：用的是 PP-StructureV3（含 PP-FormulaNet），
公式直接输出 LaTeX，∠ / ⊥ / 分数不用再靠规则猜。

跑法：
    ./ocr-local-venv/bin/python local_ocr_service.py
    # 或 ./run_local_ocr.sh
"""
import json
import os
import re
import time
from typing import Annotated, Optional

import cv2
import numpy as np

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

def _load_api_keys() -> set:
    """key 从环境变量或文件读

    文件模式（launchd 常驻用）：OCR_API_KEYS_FILE 指向一个 0600 的文件，
    一行一个 key —— 免得密钥进 launchd 的 plist。
    """
    keys = set()
    for k in os.getenv("OCR_API_KEYS", "").split(","):
        if k.strip():
            keys.add(k.strip())
    path = os.getenv("OCR_API_KEYS_FILE", "").strip()
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        keys.add(line)
        except OSError:
            pass
    return keys


API_KEYS = _load_api_keys()
MAX_BYTES = int(os.getenv("OCR_MAX_IMAGE_MB", "10")) * 1024 * 1024
ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MODEL_NAME = "PP-StructureV3(PP-FormulaNet_plus-L)"
VERSION = "0.1.0-local"


class HealthResponse(BaseModel):
    status: str
    model: str
    version: str


class OCRResponse(BaseModel):
    ok: bool
    blocks: list
    stats: dict


app = FastAPI(title="Local PaddleOCR (strong)", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

_ocr = None


def get_engine():
    global _ocr
    if _ocr is None:
        from paddleocr import PPStructureV3

        _ocr = PPStructureV3(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _ocr


# === LaTeX → 纯文本（给「复制纯文本」用）===
# 反斜杠用 chr(92) 拼出来 —— 源码里一个反斜杠字符都没有，
# 免得经过任何一层模板/转义就被吃掉（踩过：正则里的 \p 直接报 bad escape）。
BS = chr(92)

LATEX_TO_PLAIN = [
    (BS + "angle", "∠"),
    (BS + "bot", "⊥"),
    (BS + "perp", "⊥"),
    (BS + "parallel", "∥"),
    (BS + "triangle", "△"),
    (BS + "times", "×"),
    (BS + "cdot", "·"),
    (BS + "div", "÷"),
    (BS + "pm", "±"),
    (BS + "degree", "°"),
    (BS + "circ", "°"),
]


def _read_group(text: str, start: int):
    """text[start] 是 '{'，读出这一组内容，返回 (内容, 结束位置)"""
    depth = 0
    out = []
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
        out.append(ch)
        i += 1
    return "".join(out), i


def latex_to_plain(latex: str) -> str:
    """把真 LaTeX 转成能给人看的纯文本"""
    s = latex or ""

    # frac{a}{b} → a/b
    frac = BS + "frac"
    guard = 0
    while frac in s and guard < 50:
        guard += 1
        i = s.find(frac)
        j = i + len(frac)
        if j < len(s) and s[j] == "{":
            num, j = _read_group(s, j)
            if j < len(s) and s[j] == "{":
                den, j = _read_group(s, j)
                s = s[:i] + num + "/" + den + s[j:]
                continue
        s = s[:i] + s[i + len(frac):]

    # text{...} / mathrm{...} → 里面的字
    for cmd in ("text", "mathrm", "mathsf", "mathbf", "textit"):
        token = BS + cmd + "{"
        guard = 0
        while token in s and guard < 50:
            guard += 1
            i = s.find(token)
            inner, j = _read_group(s, i + len(cmd))
            s = s[:i] + inner + s[j:]

    for cmd, ch in LATEX_TO_PLAIN:
        s = s.replace(cmd, ch)

    s = s.replace("{", "").replace("}", "")
    s = s.replace(BS + BS, " ")

    # 剩下的排版命令（left/right/! 等）直接丢掉
    out = []
    i = 0
    while i < len(s):
        if s[i] == BS and i + 1 < len(s) and s[i + 1].isalpha():
            j = i + 1
            while j < len(s) and s[j].isalpha():
                j += 1
            i = j
            continue
        out.append(s[i])
        i += 1
    s = "".join(out)
    return s.replace("^", "").replace("$", "").strip()


def _bbox(value) -> list:
    """bbox 可能是 list，也可能是字符串（'[0, 17, 611, 56]'）

    不用正则 —— 源码里不放反斜杠，免得被转义层吃掉。
    """
    if isinstance(value, str):
        text = value.strip().strip("[]()")
        parts = [p for p in text.replace(";", ",").split(",") if p.strip()]
        try:
            value = [float(p) for p in parts]
        except ValueError:
            value = []
    if not value:
        return [0.0, 0.0, 0.0, 0.0]
    try:
        nums = [float(v) for v in value][:4]
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 0.0]
    while len(nums) < 4:
        nums.append(0.0)
    return nums


# === 填空横线检测（lesson-35） ===
# 填空题的横线是「画出来的线」，不是字符 —— OCR 必然读不到。
# 结果就是 "CE=" 后面没有下划线，老师拿到的是残题。
# 这里用 OpenCV 找出正文里的横向长线，再按行级坐标把它贴回原文。
#
# 图形内部的边线（图里的三角形边）要排除 —— 否则每张带图的题
# 都会被塞一堆假下划线。用 parsing_res_list 里的 image 块 bbox 排除。


def _detect_blank_lines(contents: bytes, figure_boxes: list) -> list:
    """返回正文里的横向长线 [(x, y, w, h), ...]（图形内部的线排除）"""
    try:
        buf = np.frombuffer(contents, dtype=np.uint8)
        gray = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return []
    if gray is None or gray.size == 0:
        return []
    h, w = gray.shape
    inv = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )
    # 核宽取图片宽度的 ~3%（实测 639/644 宽的题图用 20~21 正好命中横线，
    # 不会把汉字的横笔画也算进来）
    kern_w = max(16, min(30, w // 30))
    kern = cv2.getStructuringElement(cv2.MORPH_RECT, (kern_w, 1))
    horiz = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kern)
    cnts, _ = cv2.findContours(horiz, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    out = []
    for c in cnts:
        x, y, ww, hh = cv2.boundingRect(c)
        if hh > 6 or ww < 25:
            continue
        if ww < 4 * max(hh, 1):
            continue
        in_figure = False
        for fb in figure_boxes:
            if not (x + ww <= fb[0] or x >= fb[2] or y + hh <= fb[1] or y >= fb[3]):
                in_figure = True
                break
        if in_figure:
            continue
        out.append((x, y, ww, hh))
    return sorted(out, key=lambda b: (b[1], b[0]))


def _ocr_lines(payload: dict) -> list:
    """行级 OCR 结果 [(文本, (x1, y1, x2, y2)), ...]

    PP-StructureV3 的 overall_ocr_res 里 rec_texts/rec_polys 是逐行的，
    用来把横线定位到「哪一行文字后面」。
    """
    res = payload.get("overall_ocr_res") or {}
    texts = res.get("rec_texts") or []
    polys = res.get("rec_polys") or []
    lines = []
    for i, t in enumerate(texts):
        if i >= len(polys):
            break
        try:
            xs = [float(p[0]) for p in polys[i]]
            ys = [float(p[1]) for p in polys[i]]
        except Exception:
            continue
        lines.append((str(t), (min(xs), min(ys), max(xs), max(ys))))
    return lines


def _inside_math(content: str, idx: int) -> bool:
    """idx 位置是否落在 $...$ 公式段里"""
    return content.count("$", 0, idx) % 2 == 1


def _insert_blank_after_text(parsing: list, anchor_text: str) -> bool:
    """在指定文本后面插入 '____'

    若锚点落在公式 $...$ 里 → 插到公式结束符之后（公式里不能塞下划线，
    KaTeX 会报错）。返回是否插入成功。
    """
    for blk in parsing:
        if blk.get("block_label") != "text":
            continue
        content = str(blk.get("block_content") or "")
        pos = content.find(anchor_text)
        if pos < 0:
            continue
        ins = pos + len(anchor_text)
        if _inside_math(content, ins):
            close = content.find("$", ins)
            if close < 0:
                continue
            ins = close + 1
        blk["block_content"] = content[:ins] + "____" + content[ins:]
        return True
    return False


def _insert_fill_blanks(payload: dict, contents: bytes) -> int:
    """把检测到的填空横线插回原文（就地改 parsing_res_list 的 text 块）

    返回插入了几条。
    """
    parsing = payload.get("parsing_res_list") or []
    if not parsing:
        return 0
    figure_boxes = []
    for blk in parsing:
        if blk.get("block_label") == "image":
            figure_boxes.append(tuple(_bbox(blk.get("block_bbox"))))
    blanks = _detect_blank_lines(contents, figure_boxes)
    if not blanks:
        return 0
    lines = _ocr_lines(payload)
    if not lines:
        return 0

    inserted = 0
    used = set()
    for (bx, by, bw, bh) in blanks:
        anchor = None
        best = None
        for idx, (text, (x1, y1, x2, y2)) in enumerate(lines):
            if idx in used or not text.strip():
                continue
            # 同一行：横线的 y 要落在这行的上下范围内（留一点余量）
            if by < y1 - 6 or by + bh > y2 + 6:
                continue
            # 横线紧跟在某行文字右边
            if abs(bx - x2) > 25:
                continue
            if best is None or abs(bx - x2) < best:
                best = abs(bx - x2)
                anchor = (idx, text)
        if anchor is None:
            continue
        if _insert_blank_after_text(parsing, anchor[1]):
            used.add(anchor[0])
            inserted += 1
    return inserted


def _split_latex(text: str):
    """把 PP-StructureV3 的正文拆成 text 段和 formula 段

    PP-StructureV3 正文里用 $...$ 标公式，里面已经是**真 LaTeX**。
    这里直接拆开、各自带自己的块 —— 后端就不用再猜符号了。
    """
    blocks = []
    pos = 0
    for m in re.finditer(r"\$([^$]+)\$", text):
        before = text[pos:m.start()]
        if before.strip():
            blocks.append(("text", before))
        blocks.append(("formula", m.group(1)))
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        blocks.append(("text", tail))
    return blocks


def _blocks_from(payload: dict) -> list:
    out = []
    for blk in payload.get("parsing_res_list") or []:
        label = blk.get("block_label")
        content = str(blk.get("block_content") or "")
        bbox = _bbox(blk.get("block_bbox"))

        if label == "text":
            for kind, seg in _split_latex(content):
                if kind == "text":
                    out.append({"type": "text", "text": seg, "bbox": bbox, "confidence": 1.0})
                else:
                    out.append({
                        "type": "formula",
                        "latex": seg.strip(),
                        "plain": latex_to_plain(seg),
                        "bbox": bbox,
                        "confidence": 1.0,
                    })
        elif label == "formula":
            out.append({
                "type": "formula",
                "latex": content.strip(),
                "plain": latex_to_plain(content),
                "bbox": bbox,
                "confidence": 1.0,
            })
        elif label == "image":
            # 版面模型把图（三角形示意图）认成 image 块 ——
            # 它的 bbox 就是图的位置，比我们自己猜准得多
            out.append({"type": "figure", "bbox": bbox, "confidence": 1.0})
        elif label == "table":
            out.append({"type": "table", "html": content, "bbox": bbox, "confidence": 1.0})
    return out


async def verify_api_key(x_api_key: Annotated[Optional[str], Header()] = None):
    if not API_KEYS:
        return "anonymous"
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", model=MODEL_NAME, version=VERSION)


@app.post("/api/v1/ocr/image", response_model=OCRResponse)
async def ocr_image(
    image: Annotated[UploadFile, File(description="题目图片")],
    _: Annotated[str, Depends(verify_api_key)],
):
    contents = await image.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    if image.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {image.content_type}")

    import tempfile

    t0 = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(contents)
        tmp.flush()
        try:
            res = get_engine().predict(input=tmp.name)[0]
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"OCR engine error: {exc}")

    payload = res.json
    if isinstance(payload, dict) and "res" in payload:
        payload = payload["res"]

    # 填空横线补回 —— OCR 读不到「画出来的线」，这里按行级坐标贴回去
    try:
        n_blanks = _insert_fill_blanks(payload, contents)
        if n_blanks:
            print(f"[ocr] 补回填空横线 {n_blanks} 条", flush=True)
    except Exception as exc:
        print("[ocr] 填空横线检测失败(忽略):", exc, flush=True)

    blocks = _blocks_from(payload)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return OCRResponse(
        ok=True,
        blocks=blocks,
        stats={"elapsed_ms": elapsed_ms, "model": MODEL_NAME},
    )


if __name__ == "__main__":
    import uvicorn

    print("加载模型（已缓存的话几秒）...", flush=True)
    get_engine()
    print("模型就绪，启动 http://127.0.0.1:8099", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8099, workers=1, log_level="info")
