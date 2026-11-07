"""uploads/ 目录的统一解析

为什么要专门一个模块
--------------------
上传、读图、裁图、导出 PDF 现在都要找同一个 uploads/ 目录，
各写各的迟早写出两个不同的路径（一个相对 CWD、一个相对代码目录）。

规矩
----
1. 只认**裸文件名** —— 带路径的一律拒绝（防目录穿越）
2. 目录位置：优先代码同级 lesson-02/uploads，退回当前工作目录下的 uploads/
   （服务器上两者指向同一个：/opt/teacher-bank/app/uploads）
"""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent      # lesson-02/app/
BASE_DIR = APP_DIR.parent                               # lesson-02/


def uploads_dir() -> Path:
    """上传目录的绝对路径"""
    candidates = [BASE_DIR / "uploads", Path("uploads").resolve()]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def upload_file_path(filename: str) -> Path | None:
    """把裸文件名解析成 uploads/ 下的绝对路径；不合法返回 None"""
    if not filename:
        return None
    if filename != Path(filename).name:
        return None
    base = uploads_dir()
    path = base / filename
    try:
        resolved = path.resolve()
        resolved.relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return path
