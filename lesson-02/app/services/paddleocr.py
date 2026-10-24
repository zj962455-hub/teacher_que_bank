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
    调 PaddleOCR 同步接口,返回识别结果(blocks + stats)
    
    PaddleOCR 服务在阿里云 ECS,域名 lanhu-lab.top
    单图 3-10 秒,平均 5 秒
    """
    # 先做本地校验(任务 2)
    validate_image(image_path)
    
    base_url = os.getenv("PADDLEOCR_BASE_URL", "").rstrip("/")
    api_key = os.getenv("PADDLEOCR_API_KEY", "")
    
    if not base_url or not api_key:
        raise OcrError(
            "PADDLEOCR_BASE_URL / PADDLEOCR_API_KEY 未配置",
            status_code=500,
            hint="检查 lesson-02/.env 文件",
        )
    
    try:
        with open(image_path, "rb") as f:
            res = requests.post(
                f"{base_url}/api/v1/ocr/image",
                headers={"X-API-Key": api_key},
                files={"image": (os.path.basename(image_path), f, "image/jpeg")},
                timeout=60,
            )
    except requests.exceptions.Timeout:
        raise OcrError(
            "OCR 服务响应超时(60s)",
            status_code=504,
            hint="请稍后重试,或检查 ECS 服务状态",
        )
    except requests.exceptions.ConnectionError as e:
        raise OcrError(
            f"OCR 服务连接失败:{e}",
            status_code=503,
            hint="检查 ECS 服务器是否在跑 / 域名是否过期 / 防火墙",
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
            hint="PADDLEOCR_API_KEY 配置错或过期,检查 .env",
        )
    if res.status_code == 413:
        raise OcrError(
            "ECS 拒收:图片过大",
            status_code=413,
            hint="虽然本地校验过,但 ECS 端还有更严的限",
        )
    if res.status_code == 415:
        raise OcrError(
            "ECS 拒收:图片类型不支持",
            status_code=415,
            hint="虽然本地校验过,但 ECS mime 白名单不同",
        )
    if 500 <= res.status_code < 600:
        raise OcrError(
            f"ECS 服务错误({res.status_code})",
            status_code=502,
            hint="ECS 服务暂时不可用,5 分钟后重试",
        )
    
    # === 成功路径 ===
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

    # === lesson-07:把 text block 里的 Unicode 数学字符拆成 formula block ===
    # PaddleOCR 对简单公式会当成普通文字输出(如 "x²" 是 Unicode 不是 LaTeX),
    # 这里统一转成 latex 字段,前端 KaTeX 才能渲染。
    enrich_blocks(data)

    return data