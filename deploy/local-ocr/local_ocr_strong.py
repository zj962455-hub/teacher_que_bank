"""本机强模型 OCR：PPStructureV3（含 PP-FormulaNet，直接出 LaTeX）"""
import json
import sys
import time
from pathlib import Path

OUT = Path("/tmp/local_ocr")
OUT.mkdir(exist_ok=True)

from paddleocr import PPStructureV3  # noqa: E402


def payload_of(res):
    p = res.json
    if isinstance(p, dict) and "res" in p:
        p = p["res"]
    return p


print("加载 PPStructureV3（模型已缓存）...", flush=True)
ocr = PPStructureV3(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

for path in sys.argv[1:]:
    p = Path(path)
    name = p.stem
    t1 = time.time()
    try:
        res = ocr.predict(input=str(p))[0]
    except Exception as exc:
        print("FAILED %s: %s" % (name, exc), flush=True)
        continue
    took = time.time() - t1
    payload = payload_of(res)

    blocks = []
    for blk in payload.get("parsing_res_list") or []:
        blocks.append({
            "label": blk.get("block_label"),
            "content": blk.get("block_content"),
            "bbox": blk.get("block_bbox"),
        })
    formulas = payload.get("formula_res_list") or []

    (OUT / (name + ".json")).write_text(
        json.dumps({"file": str(p), "seconds": round(took, 2),
                    "parsing_res_list": blocks,
                    "formula_res_list": formulas},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("===== %s  (%.1fs) =====" % (name, took), flush=True)
    for b in blocks:
        print("  [%-7s] %s" % (b.get("label"), str(b.get("content"))[:160].replace("\n", " ")), flush=True)
    if formulas:
        print("  --- 公式块 ---", flush=True)
        for f in formulas:
            print("    *", str(f.get("latex") or f.get("rec_text"))[:120], flush=True)
