"""OCR 结果持久化层 — lesson-06 任务 3

设计要点
--------
1. **存储位置** ``uploads/ocr/{task_id}.json``
   - 放在 uploads/ 下,跟图片同一个目录树,``.gitignore`` 已覆盖 uploads/ 所以不会进 git
   - 每个任务一个文件,天然隔离,不用管并发写同一个文件

2. **完整存** 每条记录含 result + stats + image_url + created_at + status + user_id
   - image_url 是给任务 4(前端展示原图)用的关联字段,没有它就没法「哪张图对应哪次识别」
   - created_at 给人看的,排序用
   - user_id 是**归属**(谁发起的这次 OCR)——
     没有它,任何登录用户拿 task_id 就能看别人的识别结果、也能把别人的结果入库
   - ⚠️ 老记录没有 user_id 字段(上线前跑的那批)——
     它们既不属于任何人,也不该被白送给任何普通用户,只有管理员看得到

3. **启动时 load** 模块级 ``_load_all()`` 在 import 时执行一次
   - 内存 dict 重建 → 后端重启后前端轮询老 task_id 还能拿到结果
   - 只 load ``completed`` 的,``processing``/``failed`` 的不重载(重启后那些任务已经死了)

4. **失败不落盘** 只有成功的结果才写文件
   - 失败任务写文件没意义,而且会污染 history 列表
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.math_parser import latex_to_plain

# === 存储根目录 ===
# Path(__file__) = lesson-02/app/services/ocr_store.py
# parents[2] = lesson-02/  → 拼 uploads/ocr/
OCR_STORE_DIR = Path(__file__).resolve().parents[2] / "uploads" / "ocr"


def _backfill_plain(record: dict) -> None:
    """给缺失 plain 字段的历史记录补算

    背景
    ----
    plain 字段是 lesson-07 任务 2 加的(LaTeX -> Unicode 纯文本),
    是在 OCR 当场算好存进 JSON 的。
    **在 plain 字段上线之前保存的历史记录没有这个字段**。

    不补算的话,前端 buildPlainText 会 fallback 到 latex,
    老师复制出来就是 "x^{2}" 而不是 "x²"。

    幂等:有值就跳过。
    """
    # ⚠️ blocks 在 record["result"]["blocks"],不是 record["blocks"]
    #    （record 是整个任务记录,result 才是 OCR 原始返回）
    for block in record.get("result", {}).get("blocks", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "formula":
            continue
        if not block.get("plain"):
            latex = block.get("latex", "")
            block["plain"] = latex_to_plain(latex) if latex else ""


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
            _backfill_plain(data)
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
    """列出最近 N 条成功识别记录,按创建时间倒序

    ⚠️ 这是**不带归属过滤**的版本 —— 只有管理员视角(追溯历史)才用。
    给普通用户返回时一律走 ``list_history_for_user``。
    """
    records = [r for r in TASKS.values() if r.get("status") == "completed"]

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return records[:limit]


def is_task_visible(record: dict | None, user_id: int, *, is_admin: bool = False) -> bool:
    """这条 OCR 记录是不是这个人能看的

    规则(两个接口共用,别各写一套)
    --------------------------
    - 管理员 → 全部可见(含没有 user_id 的历史遗留记录,做历史追溯要用)
    - 普通用户 → 只看自己发起的(user_id 相同)
    - 历史遗留记录(没有 user_id 字段)→ **普通用户看不到**
      它们属于「上线前那批没归属的数据」,白送给任何人都算数据泄露。

    ⚠️ 越权一律当「不存在」(调用方返 404,不返 403)——
    跟 uploads 路由既有口径一致:不让外人用状态码差异探测出某个 id 存不存在。
    """
    if record is None:
        return False
    if is_admin:
        return True
    owner = record.get("user_id")
    if owner is None:
        return False
    return owner == (user_id or 0)


def list_history_for_user(user_id: int, limit: int = 10, *, is_admin: bool = False) -> list[dict]:
    """列出**这个人能看**的最近 N 条成功识别记录,按创建时间倒序

    - 普通用户:只返回自己发起的
    - 管理员:返回全部,含历史遗留(无 user_id)的记录
    """
    records = [
        r for r in TASKS.values()
        if r.get("status") == "completed"
        and is_task_visible(r, user_id, is_admin=is_admin)
    ]

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return records[:limit]

#按原图 URL 查最近一次识别结果
def get_by_image(image_url: str) -> dict | None:
    """按原图 URL 查最近一次识别结果

    ⚠️ **不按用户过滤** —— 内部/管理员视角用。
    给普通用户用之前必须先过 ``is_task_visible``（OCR 归属规则）。
    """
    records = [
        r for r in TASKS.values()
        if r.get("status") == "completed" and r.get("image_url") == image_url
    ]

    if not records:
        return None

    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    return records[0]