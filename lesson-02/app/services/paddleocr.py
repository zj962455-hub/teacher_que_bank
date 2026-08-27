import os
import requests


def recognize(image_path: str) -> dict:
    """
    调 PaddleOCR 同步接口,返回识别结果(blocks + stats)
    
    PaddleOCR 服务在阿里云 ECS,域名 lanhu-lab.top
    单图 3-10 秒,平均 5 秒
    """
    base_url = os.getenv("PADDLEOCR_BASE_URL", "").rstrip("/")
    api_key = os.getenv("PADDLEOCR_API_KEY", "")
    
    if not base_url or not api_key:
        raise RuntimeError("PADDLEOCR_BASE_URL / PADDLEOCR_API_KEY 未配置")
    
    # 透传 multipart/form-data,PaddleOCR 期望的字段名是 "image"
    with open(image_path, "rb") as f:
        res = requests.post(
            f"{base_url}/api/v1/ocr/image",
            headers={"X-API-Key": api_key},
            files={"image": (os.path.basename(image_path), f, "image/jpeg")},
            timeout=60,  # 同步等,给 60s 兜底
        )
    res.raise_for_status()
    return res.json()