"""试卷导出 JPG（每页一张图）— lesson-23

为什么要有这个
--------------
原型 ⑧ 试卷预览/导出 页面列了三个导出方式：

- 📄 导出 PDF（已有）
- 🖼️ 导出 JPG（每页一张图）—— 适合发群 / 朋友圈 / 学生平板
- 📋 复制到剪贴板

PDF 是「打印稿」，老师发到微信群想要的是一张张图片。
所以这里把**已经渲染好的 PDF** 再逐页栅格化成 JPEG，打包成 ZIP 返回。

实现要点
--------
1. **复用 PDF 那条链路**（Chromium + KaTeX + A4 分页 + 溯源页脚）
   —— 不重新实现一遍排版，图片和打印稿完全一致。
2. **pypdfium2 渲染** —— 纯 wheel，自带 pdfium，不用在服务器装 poppler。
3. **Pillow 只负责 JPEG 编码**（pypdfium2 自己只出 bitmap）。

依赖装在 /opt/teacher-bank/.venv（见 deploy/teacher-bank/01-install.sh）。
"""

import io
import zipfile


class JpgExportError(Exception):
    """JPG 导出失败"""


def pdf_to_jpegs(pdf_bytes: bytes, scale: float = 2.0, quality: int = 88) -> list[bytes]:
    """PDF 字节 → 每页一张 JPEG 的字节列表

    scale=2 → 约 144 DPI（A4 约 1190×1684 px），发群里够清晰
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # 依赖没装
        raise JpgExportError(
            "缺少依赖 pypdfium2 / Pillow，请在服务器 venv 里安装"
        ) from e

    try:
        from PIL import Image
    except ImportError as e:
        raise JpgExportError("缺少依赖 Pillow，请在服务器 venv 里安装") from e

    pages: list[bytes] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            if image.mode != "RGB":
                image = image.convert("RGB")
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality)
            pages.append(buf.getvalue())
            page.close()
    except JpgExportError:
        raise
    except Exception as e:
        raise JpgExportError(f"JPG 渲染失败：{e}") from e
    finally:
        pdf.close()

    return pages


def build_jpg_zip(pdf_bytes: bytes, prefix: str = "试卷", scale: float = 2.0) -> bytes:
    """PDF 字节 → ZIP 字节（每页一张 JPG，文件名带页码）"""
    pages = pdf_to_jpegs(pdf_bytes, scale=scale)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, data in enumerate(pages, start=1):
            zf.writestr(f"{prefix}-第{index}页.jpg", data)
    return buf.getvalue()
