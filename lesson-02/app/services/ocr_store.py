"""OCR 结果持久化层 — lesson-06 任务 3

设计要点
--------
1. **存储位置** ``uploads/ocr/{task_id}.json``
   - 放在 uploads/ 下,跟图片同一个目录树,``.gitignore`` 已覆盖 uploads/ 所以不会进 git
   - 每个任务一个文件,天然隔离,不用管并发写同一个文件

2. **完整存** 每条记录含 result + stats + image_url + created_at + status
   - image_url 是给任务 4(前端展示原图)用的关联字段,没有它就没法「哪张图对应哪次识别」
   - created_at 给人看的,排序用

3. **启动时 load** 模块级 ``_load_all()`` 在 import 时执行一次
   - 内存 dict 重建 → 后端重启后前端轮询老 task_id 还能拿到结果
   - 只 load ``completed`` 的,``processing``/``failed`` 的不重载(重启后那些任务已经死了)

4. **失败不落盘** 只有成功的结果才写文件
   - 失败任务写文件没意义,而且会污染 history 列表
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# === 存储根目录 ===
# Path(__file__) = lesson-02/app/services/ocr_store.py
# parents[2] = lesson-02/  → 拼 uploads/ocr/
OCR_STORE_DIR = Path(__file__).resolve().parents[2] / "uploads" / "ocr"


# === 启动时把已完成的记录读回内存 ===
def _load_all() -> dict[str, dict]:
    """扫描 OCR_STORE_DIR,把 completed 的记录读成 dict"""
    loaded: dict[str, dict] = {}

    if not OCR_STORE_DIR.exists():
        return loaded

    for json_file in OCR_STORE_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 文件损坏 / 读不到(权限)→ 跳过,不能因为一个坏文件炸掉整个启动
            continue

        task_id = data.get("task_id")
        # 只要 completed,processing/failed 重启后已经没有意义了
        if task_id and data.get("status") == "completed":
            loaded[task_id] = data

    return loaded


# 内存镜像(给 status 轮询用),启动时从磁盘恢复
TASKS: dict[str, dict] = _load_all()


# === 写盘 ===
def save_task(task_id: str, record: dict) -> None:
    """把一条任务记录写进内存 + 落盘(只落 completed)"""
    TASKS[task_id] = record

    if record.get("status") != "completed":
        return

    OCR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    target = OCR_STORE_DIR / f"{task_id}.json"
    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# === 读盘(给 history 接口用) ===
def list_history(limit: int = 10) -> list[dict]:
    """列出最近 N 条成功识别记录,按创建时间倒序"""
    records = [r for r in TASKS.values() if r.get("status") == "completed"]

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return records[:limit]

#按原图 URL 查最近一次识别结果
def get_by_image(image_url: str) -> dict | None:
    """按原图 URL 查最近一次识别结果"""
    records = [
        r for r in TASKS.values()
        if r.get("status") == "completed" and r.get("image_url") == image_url
    ]

    if not records:
        return None

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return records[0]