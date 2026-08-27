# Lesson 06 精简注释版 · PaddleOCR（自托管）

> 上一课:图片上传到后端存在 `uploads/`（lesson-05）。
> 这一课:**后端拿到图,代调阿里云 ECS 上的 PaddleOCR 服务,图片 → 文字 + 公式**。
>
> Phase 1 核心 demo 的关键一步——demo 给老师看的「图片 → 可编辑题目」全链路,这一课拼上了关键一块。

---

## 📍 OCR 服务在哪?

**自托管 PaddleOCR,跑在阿里云 ECS 上**（老大 2026-08-26 部署完成,2026-08-27 配 HTTPS）:

| 项 | 值 |
|----|----|
| 服务域名 | `https://lanhu-lab.top`（Let's Encrypt SSL 已签 · 2026-11-25 自动续期）|
| 内部端口 | nginx 80/443 → paddleocr-api :8080（**8080 不暴露公网**）|
| 模型 | PP-StructureV3（版面 + 公式 + 表格） |
| 端点 | `GET /api/v1/health`（免鉴权）· `POST /api/v1/ocr/image`（要 `X-API-Key`）|
| 部署目录 | `/opt/paddleocr/`（systemd unit + nginx 反代）|
| 配置文件 | `/etc/paddleocr/api.env`（存 API keys,chmod 600）|
| 部署文档 | `projects/teacher-question-bank/deploy/paddleocr/` |

> 老大自己写的项目笔记之前有讲过 Mathpix（已弃用,新版要求建组织才能拿 key）,我们改走自托管路线。**不依赖任何第三方 SaaS,API key 不外传**。

---

## 🧠 4 个核心概念（读 2 分钟）

### 1. PaddleOCR 服务 · 一个端点就够

**为什么**:PaddleOCR 服务**只暴露一个识别端点** + 一个健康检查。不像 Mathpix 给你同步/异步两种姿势——PaddleOCR 是**同步**的(发请求 → 等结果),慢是慢(3-10 秒),但走 nginx 反代 + 后端 BackgroundTasks 异步化,前端体验跟异步一样。

| 端点 | 方法 | 鉴权 | 用途 |
|------|------|------|------|
| `/api/v1/health` | GET | 否 | 健康检查,返 `{status, model, version}` |
| `/api/v1/ocr/image` | POST | **要** `X-API-Key` | 上传图片,返识别 blocks |

**类比**:Mathpix 是"便利店 + 外卖"两种;PaddleOCR 是"只给你外卖,但店家帮你叫外卖"(同步 + 我们后端异步化)。

### 2. `.env` + `python-dotenv` · 密钥管理（不变）

**为什么**:PaddleOCR 的 `X-API-Key` 是密码,绝不能写死在代码里(进了 git 就会被盗)。`.env` 是项目的"配置黑名单"——只在本机生效,加进 `.gitignore` 不上传。

**类比**:ECS 服务器的密码不会贴在门口。`.env` = 你钱包里的钥匙串,代码 = 门口机器人,代码伸手去钱包拿钥匙(读 env)而不是看门口。

```bash
# .env(在 lesson-02/ 下,跟 main.py 同目录,**不提交 git**)
PADDLEOCR_BASE_URL=https://lanhu-lab.top
PADDLEOCR_API_KEY=*** paste local_dev_key here>

# .env.example(提交 git,给团队看需要哪些 key)
PADDLEOCR_BASE_URL=
PADDLEOCR_API_KEY=
```

```python
# 读 .env
from dotenv import load_dotenv
import os

load_dotenv()  # 不带路径,默认读 cwd 的 .env(即 lesson-02/.env)

base_url = os.getenv("PADDLEOCR_BASE_URL")
api_key = os.getenv("PADDLEOCR_API_KEY")
```

依赖:`pip install python-dotenv`（lesson-01 venv 里应该已有,如未装:`pip install python-dotenv requests`）

### 3. FastAPI `BackgroundTasks` · 后端异步化

**为什么**:PaddleOCR 同步 API 平均 3-10 秒,慢的图到 15+ 秒。前端如果同步等,会卡住/超时。用 `BackgroundTasks` 让后端"接活后立刻返回 202 + 任务 id,识别完再通知前端",前端轮询状态。

**类比**:你点咖啡,店员说"好了叫号"(202 + task_id),你回座位继续刷手机,听到号再去取(轮询)。

```python
from fastapi import BackgroundTasks

@router.post("/")
async def start_ocr(image_url: str, background_tasks: BackgroundTasks):
    task_id = str(uuid4())
    tasks[task_id] = {"status": "processing", "result": None}

    # 后台跑 OCR,完成时把结果塞到 tasks[task_id]
    background_tasks.add_task(run_ocr, image_url, task_id)

    return {"task_id": task_id, "status": "processing"}
```

⚠️ **MVP 限制**:`BackgroundTasks` 是"请求处理完才跑"(进程内,简单)。真生产用 Celery + Redis(可恢复、可分布式)。**MVP 用 BackgroundTasks 够用**。

### 4. PaddleOCR 返回结构 · blocks（text / formula / table）

**为什么**:OCR 不只是"识别成纯文字"——PaddleOCR 把图分成**块**(blocks),每块有 `type`（text / formula / table）+ 内容（text / latex / html）+ 坐标(bbox)+ 置信度(confidence)。前端能根据 type 决定怎么渲染:

- `type=text` → 直接显示 `text`
- `type=formula` → 用 KaTeX 渲染 `latex`(lesson-07 接入)
- `type=table` → 直接渲染 `html`

```json
{
  "ok": true,
  "blocks": [
    {
      "type": "text",
      "text": "1. 解方程 $x^2 + 2x + 1 = 0$",
      "bbox": [50, 100, 600, 150],
      "confidence": 0.98
    },
    {
      "type": "formula",
      "latex": "x^{2} + 2x + 1 = 0",
      "bbox": [620, 100, 1100, 150],
      "confidence": 0.95
    },
    {
      "type": "table",
      "html": "<table><tr><td>1</td><td>2</td></tr></table>",
      "bbox": [50, 200, 600, 300],
      "confidence": 0.92
    }
  ],
  "stats": {
    "elapsed_ms": 4230,
    "model": "PP-StructureV3"
  }
}
```

**对比 Mathpix**:
- Mathpix: text + latex_styled + html + line_data(行级)
- PaddleOCR: blocks（块级,三种 type 分得更清楚）

前端展示用 `blocks[i].type` 路由:
- 纯文本 tab → 只显示 `type=text` 的 blocks 的 `text`
- 带公式 tab → text blocks + formula blocks(用 KaTeX 渲染 latex)
- 结构 tab → text blocks 拼接 + table blocks 的 html 直接渲染

---

## 🧭 4 个设计决策（老大拍板）

> 我先把建议写出来,老大看完改/确认:

| # | 决策点 | 选项 | 建议 | 理由 |
|---|---|---|---|---|
| 1 | **同步 vs 异步** | 同步 / 异步+轮询 | **异步+轮询** | PaddleOCR 慢(3-10 秒),同步会卡前端/超时;轮询体验跟"点咖啡等叫号"一样自然 |
| 2 | **OCR 结果存哪** | 内存 dict / 文件 JSON / 数据库 | **内存 dict** | MVP 简单;lesson-08 学数据库时再迁移。**注意**:后端重启结果丢,够 demo 用 |
| 3 | **图片怎么给 PaddleOCR** | multipart/form-data / base64 / 公网 URL | **multipart/form-data** | PaddleOCR 服务端是 `curl -F image=@file.jpg`,我们后端用 `requests.post(files={...})` 透传,简单粗暴 |
| 4 | **识别错了怎么办** | 自动重试 / 保留原图让用户改 | **保留原图 + 用户手动改** | prototype v0.2 已锁"原图保留"。MVP 不做自动重试(成本高、识别一般也不会错) |

---

## 📁 本课最终改动(C 方案:不新建 lesson-06/ 目录)

```
teacher_que_bank/
├── .env                              ← 新增(本地,不进 git)
├── .env.example                      ← 新增(模板,进 git)
├── .gitignore                        ← 改(确保 .env 已排除)
├── lesson-02/
│   └── app/
│       ├── main.py                   ← 改:注册 ocr 路由
│       ├── routers/
│       │   └── ocr.py                ← 新增(POST /api/ocr/ + GET /api/ocr/status/{task_id})
│       └── services/
│           └── paddleocr.py          ← 新增(PaddleOCR API 封装层)
└── lesson-03/
    └── src/
        ├── App.vue                   ← 改:加 OcrResult 组件
        └── components/
            └── OcrResult.vue         ← 新增(显示识别结果 + 状态轮询)
```

---

## 🚀 步骤(待老大开干)

### 步骤 0: 老大确认上面 4 个决策

默认按"建议"列走,如有改动告诉萝卜特。

### 步骤 1: 老大从 `/etc/paddleocr/api.env` 拿 PaddleOCR 本地 key

```bash
# SSH 上 ECS 看 key(老大做,或者让我列命令)
ssh root@8.160.177.222
sudo grep OCR_API_KEYS /etc/paddleocr/api.env
```

把 `local_dev_key_here`（逗号前面那个）写到本地 `lesson-02/.env`:

```bash
# lesson-02/.env(本地,不进 git)
PADDLEOCR_BASE_URL=https://lanhu-lab.top
PADDLEOCR_API_KEY=<local_dev_key_here>
```

### 步骤 2: 装 `python-dotenv` + `requests`（venv 里）

```bash
source lesson-01/venv/bin/activate
pip install python-dotenv requests
# 或 lesson-02 自己建 venv 也行(目前用的是 lesson-01 的 venv)
```

### 步骤 3: 配 `.env` + `.env.example`

`.env` 写在 **`lesson-02/`** 下（跟 main.py 同目录）—— 让 `load_dotenv()` 不带路径参数就能读到。

> ⚠️ 为什么不写项目根：其他 lesson（比如 lesson-03 前端）用不上 PADDLEOCR_API_KEY，避免全局污染。后续 lesson-08 多个模块需要时再统迁。

```bash
# 在 lesson-02/ 下创建 .env（本地,不提交）
cd /Users/rrobot/Desktop/dev/teacher_que_bank/lesson-02
cat > .env << 'EOF'
PADDLEOCR_BASE_URL=https://lanhu-lab.top
PADDLEOCR_API_KEY=<你的 key>
EOF

# .env.example(提交 git,给团队看需要哪些 key)
cat > .env.example << 'EOF'
PADDLEOCR_BASE_URL=
PADDLEOCR_API_KEY=
EOF

# 验证 .gitignore 已排除（lesson-02/.gitignore 里已经有 .env，无需修改）
git check-ignore .env && echo "✓ .env 被忽略"
```

### 步骤 4: 后端 `app/services/paddleocr.py`（API 封装层）

```python
# lesson-02/app/services/paddleocr.py
"""PaddleOCR API 封装层 - lesson-06"""
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
```

### 步骤 5: 后端 `app/routers/ocr.py`

```python
# lesson-02/app/routers/ocr.py
"""OCR 路由组 - lesson-06 重点:异步任务 + 状态轮询"""
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.services.paddleocr import recognize

router = APIRouter(prefix="/ocr", tags=["OCR"])

# === MVP:内存存任务状态(重启丢失)===
tasks: dict[str, dict] = {}

UPLOAD_DIR = Path("uploads")


def _run_ocr(task_id: str, image_path: str) -> None:
    """后台跑 OCR,完成时把结果塞到 tasks[task_id]"""
    try:
        result = recognize(image_path)
        tasks[task_id] = {
            "status": "completed",
            "result": result,
            "stats": result.get("stats", {}),
        }
    except Exception as e:
        tasks[task_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/")
async def start_ocr(payload: dict, background_tasks: BackgroundTasks):
    """
    开始 OCR 任务
    
    payload: {"image_url": "/uploads/xxx.jpg"}
    返回:{"task_id": "abc", "status": "processing"}
    """
    image_url = payload.get("image_url", "")
    if not image_url:
        raise HTTPException(400, detail="image_url 必填")
    
    # 拼本地路径(我们的 uploads/ 是相对路径)
    filename = image_url.lstrip("/").replace("uploads/", "", 1)
    image_path = UPLOAD_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(404, detail=f"图片不存在:{image_url}")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result": None}
    
    background_tasks.add_task(_run_ocr, task_id, str(image_path))
    
    return {"task_id": task_id, "status": "processing"}


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """轮询任务状态"""
    if task_id not in tasks:
        raise HTTPException(404, detail="task_id 不存在")
    return tasks[task_id]
```

### 步骤 6: 后端 `app/main.py` 注册路由 + 配 dotenv

```python
# lesson-02/app/main.py
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# === 必须在 import 其他 app 模块前 load .env ===
# .env 在 lesson-02/ 下(load_dotenv 默认读 cwd 的 .env)
load_dotenv()

from app.routers import lessons, courses, upload, ocr   # ← 加 ocr

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.3.0",
)

# === CORS + 静态挂载(lesson-04/05 已加) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# === 注册路由 ===
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")    # ← 新增


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.3.0",
    }
```

### 步骤 7: 前端 `OcrResult.vue`（本课主角）

```vue
<!-- lesson-03/src/components/OcrResult.vue -->
<script setup>
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import axios from 'axios'
import {
  NCard, NSpace, NButton, NTag, NTabs, NTabPane,
  NSpin, NAlert, NEmpty, NImage, NText,
} from 'naive-ui'

// === Props:由 UploadImage 上传成功后回传 ===
const props = defineProps({
  imageUrl: { type: String, default: '' },  // 例: /uploads/xxx.jpg
})

// === 状态 ===
const taskId = ref(null)
const status = ref('idle')      // idle / processing / completed / failed
const result = ref(null)        // PaddleOCR blocks + stats
const error = ref(null)
let pollTimer = null

// === 计算属性 ===
const textBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'text') ?? []
)
const formulaBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'formula') ?? []
)
const tableBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'table') ?? []
)

// === 开始 OCR ===
async function startOcr() {
  if (!props.imageUrl) {
    error.value = 'image_url 为空'
    return
  }
  status.value = 'processing'
  error.value = null
  result.value = null
  
  try {
    const res = await axios.post('http://localhost:8000/api/ocr/', {
      image_url: props.imageUrl,
    })
    taskId.value = res.data.task_id
    startPolling()
  } catch (e) {
    status.value = 'failed'
    error.value = `启动失败: ${e.response?.data?.detail || e.message}`
  }
}

// === 轮询状态 ===
function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const res = await axios.get(`http://localhost:8000/api/ocr/status/${taskId.value}`)
      const data = res.data
      
      if (data.status === 'completed') {
        status.value = 'completed'
        result.value = data.result
        stopPolling()
      } else if (data.status === 'failed') {
        status.value = 'failed'
        error.value = data.error || 'OCR 识别失败'
        stopPolling()
      }
      // processing 继续轮询
    } catch (e) {
      status.value = 'failed'
      error.value = `轮询失败: ${e.message}`
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(stopPolling)

// === 渲染 Markdown(MVP:简单拼接 text blocks;lesson-07 接 KaTeX 渲染公式)===
const plainText = computed(() =>
  textBlocks.value.map(b => b.text).join('\n')
)

const withFormulas = computed(() =>
  result.value?.blocks
    .filter(b => b.type === 'text' || b.type === 'formula')
    .map(b => b.type === 'formula' ? `$${b.latex}$` : b.text)
    .join('\n') ?? ''
)

// === 一键复制 ===
async function copyMarkdown() {
  await navigator.clipboard.writeText(withFormulas.value)
  // 提示用户已复制(lesson-31 UI 美化时换 NMessage)
  alert('已复制 Markdown 到剪贴板')
}
</script>

<template>
  <NCard title="🔍 OCR 识别结果" size="small">
    <NSpace vertical size="medium">
      <!-- 顶部:状态 + 原图 -->
      <NSpace align="center">
        <NTag :type="status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'info'">
          {{ status === 'idle' ? '待识别' : status === 'processing' ? '识别中...' : status === 'completed' ? '已完成' : '失败' }}
        </NTag>
        <NImage
          v-if="imageUrl"
          :src="`http://localhost:8000${imageUrl}`"
          width="80"
          height="80"
          object-fit="cover"
          style="border-radius: 4px"
        />
        <NButton type="primary" :disabled="status === 'processing' || !imageUrl" @click="startOcr">
          {{ status === 'completed' ? '🔄 重新识别' : '🚀 开始识别' }}
        </NButton>
      </NSpace>

      <!-- 错误 -->
      <NAlert v-if="error" type="error" :show-icon="false">❌ {{ error }}</NAlert>

      <!-- Loading -->
      <NSpin v-if="status === 'processing'" size="medium">
        <NEmpty description="PaddleOCR 正在识别(平均 5 秒)..." />
      </NSpin>

      <!-- 结果:三 tab -->
      <NTabs v-if="status === 'completed'" type="line" animated>
        <NTabPane name="text" tab="① 纯文本">
          <pre style="white-space: pre-wrap; font-family: system-ui">{{ plainText }}</pre>
          <NText depth="3" style="font-size: 12px">
            共 {{ textBlocks.length }} 个文本块 · {{ result?.stats?.elapsed_ms }}ms · {{ result?.stats?.model }}
          </NText>
        </NTabPane>
        <NTabPane name="formula" tab="② 带公式(Markdown)">
          <pre style="white-space: pre-wrap; font-family: monospace">{{ withFormulas }}</pre>
          <NSpace>
            <NButton size="small" @click="copyMarkdown">📋 复制 Markdown</NButton>
            <NText depth="3" style="font-size: 12px">
              {{ formulaBlocks.length }} 个公式块(lesson-07 接 KaTeX 渲染)
            </NText>
          </NSpace>
        </NTabPane>
        <NTabPane name="table" tab="③ 结构(含表格)">
          <div v-for="(b, i) in result?.blocks" :key="i">
            <div v-if="b.type === 'text'">{{ b.text }}</div>
            <div v-else-if="b.type === 'formula'" style="font-family: monospace; color: #18a058">
              {{ b.latex }}
            </div>
            <div v-else-if="b.type === 'table'" v-html="b.html" />
          </div>
        </NTabPane>
      </NTabs>
    </NSpace>
  </NCard>
</template>
```

### 步骤 8: 前端 `App.vue` 集成

```vue
<!-- lesson-03/src/App.vue -->
<script setup>
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
import OcrResult from './components/OcrResult.vue'   // ← 新增
</script>

<template>
  <div class="app">
    <h1>📚 教培题库 · 课程列表</h1>
    <LessonList />
    <UploadImage />
    <OcrResult image-url="/uploads/sample.jpg" />   <!-- ← 临时写死,lesson-XX 接 UploadImage 上传成功后回调 -->
  </div>
</template>
```

---

## 🎁 5 个动手做任务（预计 60-90 分钟）

### 任务 1: 错误处理 + 重试

`app/services/paddleocr.py` 加:
- 网络超时(`requests.exceptions.Timeout`)→ 提示"OCR 服务响应慢,请重试"
- HTTP 401 → "PADDLEOCR_API_KEY 配置错或过期"
- HTTP 5xx → 提示"ECS 服务暂时不可用,5 分钟后重试"

### 任务 2: 图片大小 / 类型预处理

PaddleOCR 接收的图片不能超过 10MB(MB 限制在 nginx + app 两层都有)。后端在 `recognize` 前检查:
- 文件 > 10MB → 直接返 413,不调服务
- 文件类型不是 image/* → 返 415

### 任务 3: OCR 结果持久化（轻量级）

MVP 内存 dict 不够用,后端重启结果丢。改进:
- 每次任务完成,把 results 写到 `uploads/ocr/{task_id}.json`
- 启动时 load 回来

### 任务 4: 前端展示原图 + 公式定位

OcrResult.vue 加:
- 左边展示原图(`NImage`),右边展示识别结果
- 鼠标 hover 公式 block → 在原图上用红框高亮(`bbox`)

### 任务 5: 一键转题目编辑器

识别完成后,"复制 Markdown"按钮把 `withFormulas` 写到剪贴板。后续 lesson-XX 接:
- 题目编辑器(富文本 + KaTeX 预览)
- 自动从 OCR 结果提取学科 / 难度(可选,用 LLM 分类)

---

## 📚 速查表

### 后端 PaddleOCR 调用

```python
import requests

# 同步调 PaddleOCR(在 app/services/paddleocr.py 里)
with open(image_path, "rb") as f:
    res = requests.post(
        "https://lanhu-lab.top/api/v1/ocr/image",
        headers={"X-API-Key": api_key},
        files={"image": (filename, f, "image/jpeg")},
        timeout=60,
    )
return res.json()
# → {"ok": True, "blocks": [...], "stats": {"elapsed_ms": ..., "model": "PP-StructureV3"}}
```

### FastAPI BackgroundTasks

```python
from fastapi import BackgroundTasks

@router.post("/")
async def start(background_tasks: BackgroundTasks):
    task_id = str(uuid4())
    tasks[task_id] = {"status": "processing"}
    background_tasks.add_task(do_work, task_id)
    return {"task_id": task_id}

def do_work(task_id):
    # 异步跑,完成后改 tasks[task_id]["status"]
    ...
```

### 前端轮询模式

```js
let timer = null

async function startTask() {
  const { task_id } = await axios.post('/api/ocr/', {image_url})
  timer = setInterval(async () => {
    const res = await axios.get(`/api/ocr/status/${task_id}`)
    if (res.data.status === 'completed' || res.data.status === 'failed') {
      clearInterval(timer)
      // 处理结果
    }
  }, 1500)
}

onUnmounted(() => { if (timer) clearInterval(timer) })
```

### .env 模式

```bash
# .env(不提交)
PADDLEOCR_BASE_URL=https://lanhu-lab.top
PADDLEOCR_API_KEY=***
```

```python
# 代码(必须在 import 其他 app 模块前)
from dotenv import load_dotenv
load_dotenv()
import os
key = os.getenv("PADDLEOCR_API_KEY")
```

### PaddleOCR 返回结构

```json
{
  "ok": true,
  "blocks": [
    {"type": "text", "text": "...", "bbox": [x1,y1,x2,y2], "confidence": 0.98},
    {"type": "formula", "latex": "...", "bbox": [...], "confidence": 0.95},
    {"type": "table", "html": "<table>...</table>", "bbox": [...], "confidence": 0.92}
  ],
  "stats": {"elapsed_ms": 4230, "model": "PP-StructureV3"}
}
```

---

## 🧠 这一课的"为什么"多说一句

前 5 课都玩**同步** —— 前端发请求,后端立刻返回结果,前端等响应。
**lesson-06 是第二个分水岭**,开始玩**异步** —— 任务交给后端"后台跑",前端轮询状态。

为什么必须异步?
- PaddleOCR 单图识别 3-10 秒
- 同步会让前端 HTTP 超时(默认 30s,但用户体验是"卡死")
- 后端 BackgroundTasks 异步 + 前端轮询 = 标准做法

**异步 vs 后台任务**(粗略对应):
- 异步(async/await) = 一个函数内多个 await,不阻塞(已学)
- 后台任务(BackgroundTasks / Celery) = 把任务甩出当前请求,前端不再等

**lesson-06 + lesson-07 + lesson-08 三步走完 = 第一个能 demo 给老师看的东西**。加油!

---

## ⚠️ 跟之前 Mathpix 版的差异(给熟悉旧笔记的老大)

| 项 | Mathpix(旧) | PaddleOCR(新) |
|----|------------|---------------|
| 服务位置 | SaaS · 海外 | **自托管 ECS · 国内** |
| API key 管理 | 账号注册 + 付费 | **本地 `/etc/paddleocr/api.env` 自动生成** |
| 鉴权 | `app_id` + `app_key` header | **`X-API-Key` 单 header** |
| 图片传递 | base64 data URI in JSON | **multipart/form-data**(curl `-F`) |
| 返回结构 | text + latex_styled + html + line_data(行级) | **blocks(块级 · text/formula/table)** |
| 公式渲染 | `latex_styled` 字段 | **formula block 的 `latex` 字段** |
| 部署成本 | $4.99/月 SaaS | **2C4G ECS(已有 · 零额外)** |
| 国内访问 | 慢/封 | **走 nginx 国内直连** |

> 之前的 `docs/mathpix-setup.md` 已标 `DEPRECATED 2026-08-26`,保留作为决策历史。