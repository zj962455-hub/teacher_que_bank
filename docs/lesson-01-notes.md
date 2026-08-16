# Lesson 01 精简注释版 · FastAPI Hello World

> 在 `lesson-01-hello-world.md` 基础上加批注。
> 老大**不需要**逐字读,跟着跑就能跑通。

---

## 🎯 本课目标

浏览器看到 `{"message":"Hello from FastAPI"}`

---

## 🧠 三个核心概念(读 30 秒)

### 1. 什么是 FastAPI?

**现代 Python Web 框架**,老大自学 Python 路上的主力武器。

```
对比 Django:           对比 Flask:
❌ 大而全,什么都管     ❌ 太简单,要自己拼装
✅ 小而精,只管 API     ✅ 现代,自带数据校验
✅ 异步支持,快         ✅ 自动生成 API 文档
```

**FastAPI 给你 3 件免费东西**:
- 🛰 **路由**: `@app.get("/xxx")` 一行就是一个 API
- 📋 **自动文档**: 跑起来就能在 `/docs` 看所有接口
- ✅ **数据校验**: 客户端发脏数据,自动 422 报错,不用自己写 if

### 2. 什么是 venv?

**虚拟环境**,给每个项目装独立的 Python 包。

**为什么要**? 你以后会有 5 个项目,每个用的 Django/FastAPI 版本不一样,装一起就打架。
venv = 给每个项目一个**独立的小房间**,互不干扰。

### 3. 什么是 uvicorn?

**Web 服务器**,专门跑 FastAPI 应用。

**类比**: FastAPI 是菜谱,uvicorn 是厨师。菜谱不动手做不出菜。
开发期用 `uvicorn --reload`,你改代码它自动重启,不用手动 Ctrl+C。

---

## 🚀 老大你要跑的 4 条命令

### 步骤 1:VS Code 打开项目目录

```bash
cd ~/Desktop/dev/teacher_question_bank
code .   # 或 cursor .
```

**建议**: 在项目根目录新建 `lesson-01/` 子目录,这课代码放这里。
后续每课一个子目录,不混乱。

```bash
mkdir lesson-01
cd lesson-01
```

### 步骤 2:建 venv + 装依赖

```bash
# 建虚拟环境(只跑一次)
python3 -m venv venv

# 激活(每次新开终端都要跑)
source venv/bin/activate
# 激活后终端前面会出现 (venv) 标记

# 装 FastAPI 和 uvicorn
pip install 'fastapi[standard]'
```

**为什么 `fastapi[standard]` 带方括号?**
- 装 FastAPI + 它的所有可选依赖(uvicorn、httpx 等)
- 一次性装齐,不用一个个装

**为什么不需要 requirements.txt?**
- 真实项目要,但这课就 2 个包,直接装就行
- 后面第 3 课会教你写 requirements.txt

### 步骤 3:写 main.py

VS Code 里新建 `main.py`,粘贴:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}

@app.get("/api/info")
def get_info():
    return {
        "project": "teacher-question-bank",
        "version": "0.1.0",
        "author": "老大",
        "lesson": "Lesson 01: Hello World",
    }
```

**代码逐行翻译**:
```python
from fastapi import FastAPI   # 引入 FastAPI 类
app = FastAPI()               # 创建一个 app 实例(就是你的 Web 应用)

@app.get("/")                 # 装饰器: 这个函数响应 GET 请求 + 路径是 /
def read_root():              # 函数名(随便起,惯例叫 read_root)
    return {"message": "..."} # 返回字典,FastAPI 自动转 JSON
```

### 步骤 4:跑起来!

```bash
uvicorn main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就 OK。

**浏览器访问**:
- <http://localhost:8000> → 看到 Hello
- <http://localhost:8000/api/info> → 看到项目信息
- <http://localhost:8000/docs> → **FastAPI 自动生成的 API 文档** ⭐

---

## 🎁 额外奖励:3 个动手做小任务

完成下面 3 个小改动,体验 FastAPI 的灵活性。

### 任务 1:加一个 lessons 列表接口

```python
@app.get("/api/lessons")
def get_lessons():
    return {
        "phase_1": [
            "第 1 课:Hello World",
            "第 2 课:FastAPI 入门",
            "第 3 课:Vue 3 入门",
            # ... 共 10 课
        ]
    }
```

**体验**: 改完保存,**uvicorn --reload 自动重启**,刷新浏览器就能看到新接口。

### 任务 2:路径参数(动态路由)

```python
@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int):  # ← 类型注解 int,FastAPI 自动校验
    return {
        "id": lesson_id,
        "title": f"第 {lesson_id} 课",
    }
```

试访问:
- `/api/lessons/5` → 返回第 5 课
- `/api/lessons/abc` → **自动 422 报错**(类型不匹配,免费校验!)

### 任务 3:查询参数(可选参数)

```python
@app.get("/api/greet")
def greet(name: str = "老大", level: int = 1):
    return {
        "message": f"你好 {name}!",
        "level": level,
        "encouragement": "💪" * level,
    }
```

试访问:
- `/api/greet` → 默认 name=老大, level=1
- `/api/greet?name=数学老师` → 自定义名字
- `/api/greet?name=萝卜特&level=5` → 💪💪💪💪💪

**体验**: FastAPI 自动帮你:
- 解析 URL 参数
- 校验类型(传非数字就报错)
- 生成 `/docs` 文档

---

## 📦 提交到 GitHub

```bash
# 在 lesson-01/ 目录里
cd ~/Desktop/dev/teacher_question_bank/lesson-01

# git 初始化(只在第一次)
git init
git add main.py
git commit -m "feat(lesson-01): FastAPI Hello World + 3 endpoints"

# 关联远程仓库
git remote add origin git@github.com:zj962455-hub/teacher_que_bank.git
git branch -M main
git push -u origin main
```

**预期**:
- 第一次 push 会让你确认 GitHub SSH key 指纹 → yes
- 然后自动 push 成功
- 浏览器打开 <https://github.com/zj962455-hub/teacher_que_bank> 能看到 main.py

---

## ✅ 验收清单(打勾算过)

- [ ] uvicorn 跑起来,浏览器看到 Hello
- [ ] `/docs` 能看到自动生成的文档
- [ ] 3 个动手做任务都跑过
- [ ] 代码 push 到 GitHub 成功

---

## ⏭️ 完成后告诉我

我帮你 review 代码,然后开始 **第 2 课:FastAPI 入门**(路由分组、请求体、错误处理、async/await)。

**永远不要硬扛**——卡住截图发我。

---

## 📚 速查表

| 命令 | 干嘛 |
|---|---|
| `python3 -m venv venv` | 建虚拟环境(只一次) |
| `source venv/bin/activate` | 激活 venv(每次新终端) |
| `deactivate` | 退出 venv |
| `pip install <包>` | 装包(要先 activate) |
| `pip list` | 看当前 venv 装了哪些包 |
| `uvicorn main:app --reload` | 跑 FastAPI 开发服务器 |
| `uvicorn main:app --reload --port 8001` | 改端口(8000 被占时) |
| `Ctrl+C` | 停 uvicorn |
| `git status` | 看哪些文件改了 |
| `git add .` | 把改动加到暂存区 |
| `git commit -m "..."` | 提交 |
| `git push` | 推到 GitHub |

---

**这一课重点不是代码,是让老大熟悉 FastAPI 的开发节奏**(改 → 保存 → 自动重启 → 浏览器看效果)。后面所有课都是这个节奏。