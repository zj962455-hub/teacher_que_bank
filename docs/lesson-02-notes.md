# Lesson 02 精简注释版 · FastAPI 进阶

> 在 lesson-01 单文件基础上,**学 4 件大事**:
> 1. 项目结构(APIRouter 分组)
> 2. Pydantic 请求体(数据校验)
> 3. 错误处理(HTTPException)
> 4. async/await 异步
>
> 这一课比 lesson-01 重要——以后所有课都用这个结构。

---

## 🧠 4 个核心概念(读 1 分钟)

### 1. APIRouter — 路由分组

**为什么**: lesson-01 把所有路由塞 main.py, 5 个还行, 50 个就乱套。APIRouter 按业务拆, main.py 只负责"组装"。

**类比**: main.py = 大堂经理, APIRouter = 各部门前台。

### 2. Pydantic 请求体 — 数据校验

**为什么**: URL 参数只适合 GET 简单查询, 实际项目要 POST JSON 传复杂数据。Pydantic 自动校验字段类型/必填/默认值,**免费防御脏数据**。

**类比**: Pydantic 模型 = 表单的"必填项 + 格式校验"。你写 Excel 表格时限定列类型, Python 里就是 Pydantic。

### 3. HTTPException — 明确报错

**为什么**: API 出错要返回**明确的状态码**(404/422/500), 不能 Python 抛异常让前端瞎猜。

**类比**: HTTPException = "404 找不着"这种标准应答。 客户问"那个商品呢", 你不能回 Python traceback。

### 4. async/await — 异步 I/O

**为什么**: FastAPI 的"Fast"来自异步。题目 OCR 要等 Mathpix 几秒、读数据库要等 SQL、写文件要等磁盘——这些**等待时间**如果用同步, 一个请求占满整个 worker。**异步**让 worker 同时处理别的请求。

**何时用**:
- ✅ 调外部 API(OCR、短信、云存储)
- ✅ 数据库查询(异步驱动)
- ❌ CPU 密集(图像处理 / 视频转码 — 这些用同步或扔到 Celery)

---

## 📁 本课最终目录结构

```
lesson-02/
├── app/
│   ├── __init__.py            # 空文件,让 app/ 成包
│   ├── main.py                # FastAPI app 实例 + include_router
│   └── routers/
│       ├── __init__.py        # 空文件
│       ├── lessons.py         # /api/lessons 路由组
│       └── questions.py       # /api/questions 路由组
└── venv/                      # 跟 lesson-01 共用一个也行
```

---

## 🚀 老大要写的代码(4 个文件)

### 步骤 1: 建目录结构

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-02
mkdir -p app/routers
touch app/__init__.py app/routers/__init__.py
```

### 步骤 2: 写 `app/routers/lessons.py`

```python
"""课程元信息路由组。"""
from fastapi import APIRouter

router = APIRouter(
    prefix="/lessons",          # 这组路由统一前缀
    tags=["课程"],              # /docs 里分组显示用
)

# 完整路径: GET /api/lessons/
@router.get("/")
def list_lessons():
    return {
        "phase_1": [
            "第 1 课:Hello World",
            "第 2 课:FastAPI 进阶",
            "第 3 课:Vue 3 入门",
        ]
    }

# 完整路径: GET /api/lessons/{lesson_id}
@router.get("/{lesson_id}")
def get_lesson(lesson_id: int):
    return {
        "id": lesson_id,
        "title": f"第 {lesson_id} 课",
    }
```

**核心点**:
- `APIRouter(prefix="/lessons")` → 这组所有路由自动有 `/lessons` 前缀
- `tags=["课程"]` → `/docs` 里会归到"课程"组,看着清晰

### 步骤 3: 写 `app/routers/questions.py`

```python
"""题目路由组 - lesson-02 重点: Pydantic + HTTPException + async"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/questions",
    tags=["题目"],
)


# === Pydantic 模型: 定义"客户端发的 JSON 长啥样" ===
class QuestionIn(BaseModel):
    """客户端创建题目时发的 JSON 格式"""
    stem: str = Field(..., min_length=1, max_length=5000,
                      description="题干")
    question_type: str = Field("SC", pattern="^(SC|FB|CA|SA)$",
                                description="题型: 单选/填空/计算/简答")
    difficulty: int = Field(2, ge=1, le=3, description="难度 1-3")

# === 模拟数据(后期换成数据库) ===
fake_questions = {
    1: {"id": 1, "stem": "1+1=?", "answer": "2"},
    2: {"id": 2, "stem": "sin 30°=?", "answer": "1/2"},
}


# === 列表查询(异步版 - 演示 async/await) ===
@router.get("/")
async def list_questions():
    """异步版 - 假装从数据库读"""
    # await asyncio.sleep(0.1)  # 真实场景会等数据库
    return {"items": list(fake_questions.values()), "total": len(fake_questions)}


# === 详情查询(带错误处理) ===
@router.get("/{question_id}")
def get_question(question_id: int):
    """找不到就 404, 不让前端瞎猜"""
    q = fake_questions.get(question_id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=f"题目 ID {question_id} 不存在"
        )
    return q


# === 创建题目(POST + Pydantic 自动校验) ===
@router.post("/", status_code=201)  # 201 Created 是 POST 的标准返回
def create_question(q: QuestionIn):
    """客户端发 JSON, Pydantic 自动校验字段"""
    new_id = max(fake_questions.keys()) + 1
    fake_questions[new_id] = {
        "id": new_id,
        "stem": q.stem,
        "answer": "(待填写)",  # 答案后面再编辑
    }
    return fake_questions[new_id]
```

**核心点**:
- `BaseModel` 定义数据形状, `Field(...)` 加约束(min/max/正则/范围)
- `async def` 让函数异步, await 后能"放手"让 worker 处理别的请求
- `HTTPException(status_code=404, detail=...)` 标准错误返回

### 步骤 4: 写 `app/main.py`(替代 lesson-01 的 main.py)

```python
"""FastAPI 应用入口 - 负责组装,不写业务"""
from fastapi import FastAPI
from app.routers import lessons, questions

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.1.0",
)

# 注册路由组
app.include_router(lessons.router, prefix="/api")
app.include_router(questions.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.1.0",
    }
```

**核心点**:
- main.py 只做"组装", 不写业务逻辑(各 router 自己负责)
- `include_router(..., prefix="/api")` → 所有路由前面再加 `/api`
- 完整路径 = `/api` + router.prefix + 路由路径 → `/api/questions/`

### 步骤 5: 跑起来

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-02
# 复用 lesson-01 的 venv(已经装了 fastapi),或者建新的
source ../lesson-01/venv/bin/activate
uvicorn app.main:app --reload
```

**注意**: 启动命令变了!
- lesson-01: `uvicorn main:app --reload`
- lesson-02: `uvicorn app.main:app --reload` ← **多了一层 `app.`**

`uvicorn <python路径>:<变量名>` —— `app.main` 表示 `app/main.py`, `app` 表示那个文件里的 `app = FastAPI()`。

---

## 🎁 4 个动手做任务(预计 30-60 分钟)

### 任务 1: 测试 GET /api/questions/(异步版)
```bash
curl http://localhost:8000/api/questions/
```
期望看到 2 条假数据。

### 任务 2: 测试 POST 创建题目
```bash
curl -X POST http://localhost:8000/api/questions/ \
  -H "Content-Type: application/json" \
  -d '{"stem": "求解 x² = 4", "question_type": "CA", "difficulty": 2}'
```
期望返回 201 + 新题目 ID。

### 任务 3: 测试 Pydantic 自动校验
```bash
# 故意发脏数据
curl -X POST http://localhost:8000/api/questions/ \
  -H "Content-Type: application/json" \
  -d '{"stem": "", "question_type": "INVALID", "difficulty": 99}'
```
期望看到 **422 错误 + 详细校验信息**(免费防御!)。

### 任务 4: 测试 404 错误处理
```bash
curl http://localhost:8000/api/questions/9999
```
期望看到 **404 + "题目 ID 9999 不存在"**。

### 任务 5(可选): 异步的实际差异
写一个同步版 list_questions 和异步版, 在 `/docs` 看接口描述区别。然后读 lesson 文档里的"何时用 async" 那段。

---

## 📦 提交到 GitHub

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-02
git init
# 写 .gitignore(参考 lesson-01/lesson-01/.gitignore)
git add app/
git commit -m "feat(lesson-02): APIRouter + Pydantic + HTTPException + async"

git remote add origin git@github.com:zj962455-hub/teacher_que_bank.git
git branch -M main
git push -u origin main
```

---

## ✅ 验收清单

- [ ] 项目结构按 4 个文件组织(main.py + 2 个 router + main 组装)
- [ ] `GET /api/lessons/` 返回课程列表
- [ ] `GET /api/questions/` 异步版能跑
- [ ] `POST /api/questions/` 创建题目 + Pydantic 校验生效
- [ ] `GET /api/questions/9999` 返回 404 + 中文 detail
- [ ] 故意发脏数据看到 422
- [ ] 代码 push 到 GitHub

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | 启动命令是 `uvicorn app.main:app`,不是 `uvicorn main:app` |
| Pydantic 报错 `Field(...)` | 确认 `from pydantic import BaseModel, Field` |
| async 函数不能用 `def` | 反过来, `async def` 才行 |
| 中文 detail 在 /docs 里乱码 | 浏览器层面问题,不影响 API |

---

## ⏭️ 完成后

我帮你 review + 开始 **Lesson 03: Vue 3 入门**(组件 / ref / reactive / 第一个列表页)。

---

## 📚 速查表

```python
# 路由分组
router = APIRouter(prefix="/xxx", tags=["组名"])
@router.get("/")              # GET
@router.post("/", status_code=201)  # POST
@router.put("/{id}")          # 全量更新
@router.patch("/{id}")        # 部分更新
@router.delete("/{id}")       # 删除

# Pydantic
class MyModel(BaseModel):
    name: str                       # 必填字符串
    age: int = 18                   # 可选, 默认 18
    email: str | None = None        # 可空
    tags: list[str] = []            # 列表默认空
    score: float = Field(0.0, ge=0, le=100)  # 0-100

# 错误
raise HTTPException(status_code=404, detail="找不到")
raise HTTPException(status_code=422, detail="数据有问题")

# 异步
async def fetch():                 # 异步函数
    result = await some_io()        # await 一个 I/O 操作
    return result
```

---

## 🧠 这一课的"为什么"再多说一句

按理 lesson-02 可以拆成 4 课(每课一个概念), 但老大风格是"读完赶紧上手", 所以**一次性给你看全**。每课你重点记住:
- 看到 `@router.xxx` → 知道是路由
- 看到 `BaseModel` → 知道是数据形状
- 看到 `HTTPException` → 知道是错误处理
- 看到 `async def` → 知道是异步 I/O

**后面所有课都用这套结构**。你习惯了, 后面的速度会飞快。

晚安! 🌙