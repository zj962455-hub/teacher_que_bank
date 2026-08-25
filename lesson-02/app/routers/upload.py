import os
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(
    prefix="/upload",
    tags=["图片上传"],
)

UPLOAD_DIR = "uploads"

# === 确保 uploads 目录存在 ===
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def upload_image(file: UploadFile = File(...)):
    """
    接收图片上传,存到本地 uploads/ 目录,返回访问 URL
    
    - 前端发: multipart/form-data,字段名 'file'
    - 后端存: uploads/{timestamp}_{原文件名}
    - 返回: {filename, url, size, content_type}
    """
    # 类型检查(只允许图片)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"只支持图片,收到 {file.content_type}")
    
    # 生成唯一文件名(避免重名覆盖)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, safe_filename)
    
    # 写文件
    content = await file.read()
     # === 大小校验(5 MB 上限)===
    MAX_SIZE = 5 * 1024 * 1024
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 5 MB 限制(当前 {len(content) // (1024 * 1024)} MB)"
        )
    with open(filepath, "wb") as f:
        f.write(content)
    
    return {
        "filename": safe_filename,
        "url": f"/uploads/{safe_filename}",
        "size": len(content),
        "content_type": file.content_type,
    }


@router.get("/list")
def list_uploads():
    """列出所有已上传的图片(供前端展示历史)"""
    files = sorted(os.listdir(UPLOAD_DIR), reverse=True)  # 最新在前
    return [
        {
            "filename": f,
            "url": f"/uploads/{f}",
        }
        for f in files
        if not f.startswith(".")  # 过滤隐藏文件(.DS_Store 等)
    ]