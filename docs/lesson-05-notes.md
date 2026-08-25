# Lesson 05 精简注释版 · 图片上传 + FormData

> 在 lesson-04 前后端打通 + axios 基础上,**学 4 件大事**:
> 1. **File API** — `<input type="file">` 拿 File 对象
> 2. **FormData** — 装文件的容器,multipart/form-data
> 3. **FileReader** — 把 File 转 base64 显示预览
> 4. **FastAPI UploadFile** — 后端接收 + `python-multipart` 依赖
>
> 这一课把"图片"接进来——前面所有课都玩文本/JSON,lesson-05 开始玩二进制。

---

## 🧠 4 个核心概念(读 1 分钟)

### 1. File API — 拿文件对象

**为什么**: 浏览器需要把"用户在文件选择器里挑的文件"变成 JS 能操作的对象。

**类比**: Python 里 `open(file, 'rb')` 拿到文件句柄——浏览器里是 `<input type="file">` + `change` 事件 + `e.target.files[0]`。

```js
function onFileChange(e) {
  const file = e.target.files[0]   // File 对象
  console.log(file.name)            // "math_homework.jpg"
  console.log(file.size)            // 字节数
  console.log(file.type)            // "image/jpeg"
}
```

### 2. FormData — 装文件 + 字段

**为什么**: HTTP 默认是 JSON,但 JSON 不能装文件(文件是二进制,JSON 是文本)。`FormData` 是浏览器原生的「multipart/form-data」编码容器,专门装文件 + 普通字段。

**类比**: HTML `<form enctype="multipart/form-data">`——只不过用 JS 控制,不用真的 submit 表单。

```js
const formData = new FormData()
formData.append('file', fileObject)        // 装文件
formData.append('note', '第 5 题')          // 装字段

await axios.post('/api/upload', formData)
// axios 自动检测 FormData → 自动设 Content-Type: multipart/form-data
```

### 3. FileReader — File 转 base64 预览

**为什么**: 浏览器有"同源策略"管 HTTP,但 FileReader 是浏览器内 API,本地文件直接读成 base64 → 立刻 `<img>` 显示,**不用先上传到服务器**。

**类比**: Python 里 `base64.b64encode(open(file, 'rb').read())`——前端版的"读图转 base64"。

```js
const reader = new FileReader()
reader.onload = (e) => {
  previewUrl.value = e.target.result   // "data:image/jpeg;base64,/9j/4AAQ..."
}
reader.readAsDataURL(file)
```

`<img :src="previewUrl">` 直接显示——base64 嵌在 src 里,**不走 HTTP**。

### 4. FastAPI UploadFile — 后端接收文件

**为什么**: FastAPI 用 `UploadFile` 类型标注接收文件 + 自动解析 multipart。**配套要装 `python-multipart`**(不然 FastAPI 没法解析 multipart 编码)。

**类比**: Python 后端 Flask 用 `request.files['file']`——FastAPI 用 `file: UploadFile = File(...)`,效果一样。

```python
from fastapi import UploadFile, File

@router.post("/")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()                # 异步读字节
    with open("uploads/foo.jpg", "wb") as f:
        f.write(content)
    return {"filename": file.filename, "size": len(content)}
```

---

## 📁 本课最终改动(C 方案:不新建 lesson-05/ 目录)

```
teacher_que_bank/
├── lesson-02/                              ← 后端改动
│   ├── app/
│   │   ├── main.py                          ← 注册 upload 路由 + 挂 /uploads/ 静态目录
│   │   └── routers/
│   │       └── upload.py                    ← 新增(POST /api/upload/ + GET /api/upload/list)
│   └── uploads/                             ← 新增目录(图片存这里,gitignore)
└── lesson-03/                              ← 前端改动
    └── src/
        ├── App.vue                          ← 改:引入 UploadImage 组件
        └── components/
            └── UploadImage.vue              ← 新增(本课主角)
```

**为什么 lesson-05 不建目录**: 同 lesson-04 —— lesson-XX 是 lesson-02/03 的**增量**,C 方案线性累加,不是平行多份。

**`.gitignore` 提醒**: lesson-02 加 `uploads/` 到 .gitignore —— 上传的图片不进 git(防止仓库膨胀)。

---

## 🚀 老大要做的步骤(5 步)

### 步骤 1: 装 `python-multipart`

FastAPI 解析 multipart 需要这个依赖:

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-02
source ../lesson-01/venv/bin/activate
pip install python-multipart
```

会改 `lesson-01/venv/` 里的依赖(在 venv 里,不动全局 Python)。

### 步骤 2: 后端新增 `lesson-02/app/routers/upload.py`

```python
"""图片上传路由组 - lesson-05 重点:接 multipart/form-data"""
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
```

**注意**:
- 字段名 `file: UploadFile = File(...)` —— 字段名要和前端 `formData.append('file', ...)` **完全一致**,否则 422
- `file.content_type` —— 浏览器自动填的 MIME 类型(`image/jpeg` 等)
- `await file.read()` —— 异步读字节(不阻塞 event loop)
- 时间戳前缀 —— 防重名覆盖(同一个原文件名多次上传不会冲突)

### 步骤 3: 后端改 `lesson-02/app/main.py` —— 注册 upload + 挂静态目录

```python
"""FastAPI 应用入口 - 负责组装,不写业务"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import lessons, courses, upload

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.2.0",
)

# === CORS 中间件(lesson-04 已加) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 静态文件挂载(lesson-05 新增) ===
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# === 注册路由 ===
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(upload.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.2.0",
    }
```

**核心点**:
- `app.mount("/uploads", StaticFiles(...))` —— 把 `uploads/` 目录挂到 HTTP `/uploads/` 路径
- 这样后端存的图片,前端能直接通过 `http://localhost:8000/uploads/{filename}` 访问
- `StaticFiles` 是 FastAPI 内置静态文件服务,跟 Nginx 一样简单

### 步骤 4: 前端新增 `lesson-03/src/components/UploadImage.vue`

```vue
<script setup>
import { ref } from 'vue'
import axios from 'axios'

// === 状态 ===
const file = ref(null)                  // 用户选的 File 对象
const previewUrl = ref('')              // FileReader 读出的 base64 预览
const uploadedUrl = ref('')             // 上传成功后后端返回的 URL
const uploading = ref(false)            // 上传中
const error = ref(null)                 // 错误信息

// === 选文件后立刻预览 ===
function onFileChange(e) {
  const selected = e.target.files[0]
  if (!selected) return
  
  file.value = selected
  uploadedUrl.value = ''                // 换文件后清掉之前的上传结果
  error.value = null
  
  // FileReader 读成 base64 → 显示预览(不调后端,纯前端)
  const reader = new FileReader()
  reader.onload = (e) => {
    previewUrl.value = e.target.result   // "data:image/jpeg;base64,..."
  }
  reader.readAsDataURL(selected)
}

// === 上传到后端 ===
async function upload() {
  if (!file.value) {
    error.value = '请先选文件'
    return
  }
  
  uploading.value = true
  error.value = null
  
  try {
    const formData = new FormData()
    formData.append('file', file.value)
    
    const res = await axios.post(
      'http://localhost:8000/api/upload/',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,                   // 30 秒(图片可能大)
      }
    )
    uploadedUrl.value = res.data.url     // "/uploads/20260817_xxx.jpg"
  } catch (e) {
    error.value = `上传失败: ${e.response?.data?.detail || e.message}`
  } finally {
    uploading.value = false
  }
}

// === 重置 ===
function reset() {
  file.value = null
  previewUrl.value = ''
  uploadedUrl.value = ''
  error.value = null
}
</script>

<template>
  <div class="upload-image">
    <h2>📤 上传题目图片</h2>
    
    <!-- 文件选择器 -->
    <div class="file-input">
      <input 
        type="file" 
        accept="image/*" 
        @change="onFileChange"
        data-testid="file-input"
      />
      <span v-if="file" class="filename">
        {{ file.name }} ({{ Math.round(file.size / 1024) }} KB)
      </span>
    </div>
    
    <!-- 预览(选完立刻显示,没上传) -->
    <div v-if="previewUrl" class="preview">
      <h4>📋 预览:</h4>
      <img :src="previewUrl" alt="预览" />
    </div>
    
    <!-- 操作按钮 -->
    <div class="actions">
      <button 
        @click="upload" 
        :disabled="!file || uploading"
        class="primary"
      >
        {{ uploading ? '⏳ 上传中...' : '📤 上传' }}
      </button>
      <button v-if="file || previewUrl" @click="reset" class="secondary">
        ↻ 重置
      </button>
    </div>
    
    <!-- 错误 -->
    <div v-if="error" class="error">❌ {{ error }}</div>
    
    <!-- 上传成功 -->
    <div v-if="uploadedUrl" class="uploaded">
      <h4>✅ 已上传:</h4>
      <img :src="`http://localhost:8000${uploadedUrl}`" alt="已上传" />
      <p class="url">
        URL: <code>{{ uploadedUrl }}</code>
      </p>
    </div>
  </div>
</template>

<style scoped>
.upload-image { padding: 16px; border: 1px solid #ddd; border-radius: 8px; margin-top: 16px; }
.file-input { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.filename { color: #666; font-size: 14px; }
.preview, .uploaded { margin: 16px 0; }
.preview img, .uploaded img { 
  max-width: 400px; max-height: 300px; 
  border: 1px solid #ddd; border-radius: 4px;
}
.actions { display: flex; gap: 8px; margin-top: 16px; }
button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
button.primary { background: #42b883; color: white; }
button.primary:disabled { background: #ccc; cursor: not-allowed; }
button.secondary { background: #eee; color: #333; }
.error { color: #c00; margin-top: 12px; }
.url code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
</style>
```

**核心点**:
- `accept="image/*"` —— 文件选择器只显示图片(浏览器原生限制,不是强校验)
- `FileReader.readAsDataURL` —— 读 base64 给 `<img :src>` 用
- `FormData.append('file', ...)` —— 字段名要和后端 `File(...)` 一致
- `e.response?.data?.detail` —— FastAPI 错误格式 `{detail: "..."}`
- 上传后用 `http://localhost:8000${uploadedUrl}` 拼绝对路径显示图片

### 步骤 5: 前端改 `lesson-03/src/App.vue` 集成新组件

```vue
<script setup>
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
</script>

<template>
  <div class="app">
    <h1>📚 教培题库 · 课程列表</h1>
    <LessonList />
    <UploadImage />
  </div>
</template>

<style>
.app { max-width: 800px; margin: 0 auto; padding: 24px; font-family: system-ui; }
</style>
```

LessonList 不动,只加 `<UploadImage />`。

---

## 🎁 5 个动手做任务(预计 45-90 分钟)

### 任务 1: 上传进度条

`axios.post` 加 `onUploadProgress` 回调,显示百分比:

```js
const res = await axios.post(url, formData, {
  onUploadProgress: (e) => {
    const percent = Math.round((e.loaded / e.total) * 100)
    progress.value = percent   // 用一个 ref 显示 "上传中 45%"
  },
})
```

模板加: `<div v-if="uploading">⏳ 上传中 {{ progress }}%</div>`

### 任务 2: 多图上传

`<input type="file" multiple>` + 循环 append:

```vue
<input type="file" accept="image/*" multiple @change="onFilesChange" />
```

```js
function onFilesChange(e) {
  const files = Array.from(e.target.files)
  files.forEach(f => {
    const reader = new FileReader()
    reader.onload = (e) => previews.value.push({ name: f.name, url: e.target.result })
    reader.readAsDataURL(f)
  })
  fileList.value = files
}
```

后端循环处理:`for file in files: await upload(file)` 或前端并发 `Promise.all`。

### 任务 3: 文件大小/类型限制

前端:
```js
const MAX_SIZE = 5 * 1024 * 1024   // 5 MB
if (selected.size > MAX_SIZE) {
  error.value = `文件超过 5 MB(当前 ${Math.round(selected.size / 1024 / 1024)} MB)`
  return
}
```

后端(`routers/upload.py` 加):
```python
MAX_SIZE = 5 * 1024 * 1024

@router.post("/")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"文件超过 5 MB")
    ...
```

### 任务 4: 拖拽上传

```vue
<div 
  class="dropzone"
  @dragover.prevent
  @drop.prevent="onDrop"
>
  拖拽图片到此处,或点击选择
</div>
```

```js
function onDrop(e) {
  const droppedFile = e.dataTransfer.files[0]
  // 复用 onFileChange 的预览逻辑
  onFileChange({ target: { files: [droppedFile] } })
}
```

### 任务 5(可选): 上传后展示历史列表

调 `/api/upload/list` 显示所有上传过的图片(简易画廊)。

---

## 📦 提交到 GitHub

```bash
cd ~/Desktop/dev/teacher_question_bank

# 后端改动
git add lesson-02/app/main.py \
        lesson-02/app/routers/upload.py

# 前端改动
git add lesson-03/src/App.vue \
        lesson-03/src/components/UploadImage.vue

git commit -m "feat(lesson-05): 图片上传 + FormData + FastAPI UploadFile + 静态挂载"

git push origin main
```

`.gitignore` 提醒(可选,下次 commit 顺手加):
```bash
echo "uploads/" >> lesson-02/.gitignore
git add lesson-02/.gitignore
# 和 lesson-05 commit 分开,或一起都行
```

---

## ✅ 验收清单

- [ ] `python-multipart` 装好
- [ ] 后端 `routers/upload.py` 创建,`POST /api/upload/` 接收图片
- [ ] 后端 `main.py` 挂载 `/uploads/` 静态目录
- [ ] FastAPI 启动后,`curl -X POST -F "file=@/path/to/image.jpg" http://localhost:8000/api/upload/` 返回 JSON
- [ ] 前端 `UploadImage.vue` 创建,选文件有预览
- [ ] Vite 页面能看到上传组件
- [ ] 上传成功后页面显示图片 + URL
- [ ] 浏览器直接打开返回的 URL 能看到图片(静态挂载生效)
- [ ] 至少做完任务 1-2
- [ ] 代码 push 到 GitHub(不需 force)

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| **422 Unprocessable Entity** | 字段名对不上!确认前端 `formData.append('file', ...)` 和后端 `file: UploadFile = File(...)` 名字**完全一致** |
| **上传后图片 404** | `/uploads/` 静态挂载没加,或 `os.makedirs` 没在 main.py 里执行 |
| **CORS 报错** | CORS 中间件没启用(lesson-04 已配,理论不该出问题) |
| **`python-multipart` not installed** | 没装依赖,FastAPI 启动会警告:`pip install python-multipart` |
| **图片显示但传不上去** | 浏览器 DevTools → Network → 看上传请求,Form Data 标签页能看到字段名 |
| **预览不显示** | FileReader.onload 没绑定,或绑错对象 |
| **大文件上传超时** | lesson-05 默认 30 秒,大文件改 `timeout: 60000` |
| **重复上传同名文件** | 后端有 timestamp 前缀,不会冲突(用户可能困惑,但不报错) |

---

## ⏭️ 完成后

我帮你 review + 开始 **Lesson 06: 调 OCR**(Mathpix API + 异步识别 + 识别结果回填题库)。

Phase 1 的逻辑链:
```
lesson-05 上传图片      ✓
   ↓
lesson-06 调 OCR         ← 下一站
   ↓
lesson-07 显示 + 存库 + 导出 PDF
```

---

## 📚 速查表

### 前端

```js
// File 对象
const file = e.target.files[0]
file.name / file.size / file.type

// FileReader 预览
const reader = new FileReader()
reader.onload = (e) => previewUrl.value = e.target.result
reader.readAsDataURL(file)

// FormData 上传
const formData = new FormData()
formData.append('file', file)
const res = await axios.post('/api/upload/', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 30000,
})

// 进度条
onUploadProgress: (e) => {
  const percent = Math.round((e.loaded / e.total) * 100)
}

// 错误处理(axios)
error.response?.data?.detail    // FastAPI 错误格式 {detail: "..."}
```

### 后端

```python
# FastAPI 接收文件
from fastapi import UploadFile, File

@router.post("/")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()                    # 读字节
    with open(filepath, "wb") as f:                # 写盘
        f.write(content)

# 静态文件挂载
from fastapi.staticfiles import StaticFiles
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 文件类型检查
if not file.content_type.startswith("image/"):
    raise HTTPException(400, "只支持图片")

# 错误响应
raise HTTPException(status_code=413, detail="文件过大")
```

---

## 🧠 这一课的"为什么"多说一句

前面所有课都玩「文本/JSON」——lesson-04 调 `/api/courses/` 返回的是对象数组。
**lesson-05 是分水岭**,开始玩「二进制」(图片):

- 浏览器端:`File` 对象 + `FormData` 编码 + `FileReader` 预览
- 网络层:HTTP `multipart/form-data` 编码(不是 application/json)
- 服务端:`UploadFile` + `python-multipart` 解析
- 静态托管:`StaticFiles` 把存的图暴露成 URL

这四件事串起来,就是「图片从浏览器到后端」的完整链路。后面 lesson-06 OCR 拿到图识别,lesson-07 识别结果存数据库,核心还是这套链路。
