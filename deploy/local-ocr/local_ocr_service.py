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

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

API_KEYS = {k.strip() for k in os.getenv("OCR_API_KEYS", "").split(",") if k.strip()}
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
