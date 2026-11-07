# lesson-02/app/services/paddleocr.py
"""PaddleOCR API 封装层 - lesson-06 + 任务 1+2 错误处理与限制"""
import os
import mimetypes
import requests
from pathlib import Path

from app.services.math_parser import enrich_blocks

# === 任务 2:常量 ===
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB(跟 nginx + paddleocr app 一致)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


class OcrError(Exception):
    """OCR 业务错误基类"""
    def __init__(self, message: str, status_code: int = 500, hint: str = ""):
        self.message = message
        self.status_code = status_code
        self.hint = hint
        super().__init__(self._format())
    
    def _format(self) -> str:
        if self.hint:
            return f"{self.message} · 提示:{self.hint}"
        return self.message


# === 任务 2:图片大小 + 类型预处理 ===
def validate_image(image_path: str) -> None:
    """检查图片大小和类型,不合格直接抛 OcrError(不调 OCR)"""
    p = Path(image_path)
    
    if not p.exists():
        raise OcrError(f"图片不存在:{image_path}", status_code=404)
    
    # 大小检查
    size = p.stat().st_size
    if size > MAX_FILE_SIZE:
        raise OcrError(
            f"图片过大:{size / 1024 / 1024:.1f}MB (上限 {MAX_FILE_SIZE // 1024 // 1024}MB)",
            status_code=413,
            hint="请压缩后再上传",
        )
    
    # 类型检查(用 mime 推断)
    mime, _ = mimetypes.guess_type(str(p))
    if mime not in ALLOWED_IMAGE_TYPES:
        raise OcrError(
            f"图片类型不支持:{mime or '未知'}",
            status_code=415,
            hint=f"支持的类型:{', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
        )


# === 任务 1:分类错误处理 ===
def recognize(image_path: str) -> dict:
    """
    调 OCR 服务,返回识别结果(blocks + stats)

    两个引擎
    --------
    - **强模型**: 本机 M4 跑 PP-StructureV3(含 PP-FormulaNet),
      ECS 通过反向隧道访问 —— 符号/分数/公式准,单张 18~21 秒
    - **轻量模型**: ECS 本机 PP-OCRv4 mobile —— 2~4 秒,兜底

    强模型不可用(隧道断了/Mac 关机/超时)时**自动回落**轻量模型,
    线上永不掉线 —— 这也正是当初没把线上直接换成重模型的原因。
    """
    validate_image(image_path)

    strong_url = os.getenv("PADDLEOCR_STRONG_BASE_URL", "").rstrip("/")
    strong_key = os.getenv("PADDLEOCR_STRONG_API_KEY", "")
    base_url = os.getenv("PADDLEOCR_BASE_URL", "").rstrip("/")
    api_key = os.getenv("PADDLEOCR_API_KEY", "")

    if strong_url and strong_key:
        try:
            data = _post_ocr(strong_url, strong_key, image_path, timeout=90)
            data.setdefault("stats", {})["engine"] = "strong"
            enrich_blocks(data)
            return data
        except OcrError as exc:
            # 强模型挂了不能影响老师用题 —— 回落轻量模型
            print(f"[ocr] 强模型不可用,回落轻量模型: {exc}")

    if not base_url or not api_key:
        raise OcrError(
            "PADDLEOCR_BASE_URL / PADDLEOCR_API_KEY 未配置",
            status_code=500,
            hint="检查 /etc/teacherbank/app.env",
        )

    data = _post_ocr(base_url, api_key, image_path, timeout=60)
    data.setdefault("stats", {})["engine"] = "light"
    enrich_blocks(data)
    return data


def _post_ocr(base_url: str, api_key: str, image_path: str, timeout: int) -> dict:
    """真正发一次请求(两个引擎共用),失败一律抛 OcrError"""
    try:
        with open(image_path, "rb") as f:
            res = requests.post(
                f"{base_url}/api/v1/ocr/image",
                headers={"X-API-Key": api_key},
                files={"image": (os.path.basename(image_path), f, "image/jpeg")},
                timeout=timeout,
            )
    except requests.exceptions.Timeout:
        raise OcrError(
            f"OCR 服务响应超时({timeout}s)",
            status_code=504,
            hint="请稍后重试,或检查 OCR 服务状态",
        )
    except requests.exceptions.ConnectionError as e:
        raise OcrError(
            f"OCR 服务连接失败:{e}",
            status_code=503,
            hint="检查 OCR 服务是否在跑 / 隧道是否断了",
        )
    except requests.exceptions.RequestException as e:
        raise OcrError(
            f"OCR 请求异常:{e}",
            status_code=500,
            hint="网络问题或服务异常",
        )

    # === HTTP 错误码分类 ===
    if res.status_code == 401:
        raise OcrError(
            "OCR 鉴权失败(401)",
            status_code=401,
            hint="API key 配置错或过期",
        )
    if res.status_code == 413:
        raise OcrError(
            "拒收:图片过大",
            status_code=413,
            hint="虽然本地校验过,服务端还有更严的限",
        )
    if res.status_code == 415:
        raise OcrError(
            "拒收:图片类型不支持",
            status_code=415,
            hint="虽然本地校验过,服务端 mime 白名单不同",
        )
    if 500 <= res.status_code < 600:
        raise OcrError(
            f"OCR 服务错误({res.status_code})",
            status_code=502,
            hint="OCR 服务暂时不可用,稍后重试",
        )

    try:
        data = res.json()
    except requests.exceptions.JSONDecodeError:
        raise OcrError(
            "OCR 响应不是有效 JSON",
            status_code=500,
            hint=f"原始响应:{res.text[:200]}",
        )

    if not data.get("ok"):
        raise OcrError(
            f"OCR 业务失败:{data.get('error', '未知错误')}",
            status_code=500,
        )

    return data