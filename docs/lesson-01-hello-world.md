# 第 1 课：环境搭建 + Hello World

> **目标**：浏览器看到 `{"message":"Hello from FastAPI"}`
> **预计时间**：30-60 分钟
> **老大本地环境**：Homebrew ✅ / Python 3.13.3 ✅ / Node 22 ✅ / Git ✅ / VS Code ✅
> **老大服务器**：Ubuntu，已初始化，**待验证**

---

## 📦 你会学到

- 验证本地 + 服务器环境
- 创建 Python 虚拟环境（venv）
- 写第一个 FastAPI 应用
- 用 uvicorn 启动 Web 服务
- 提交代码到 GitHub

---

## 1️⃣ 本地环境（macOS — 老大专用版）

老大本地已经装好 80%，**只补缺的**：

### 1.1 装 PostgreSQL（暂跳过，第 8 课再用）

### 1.2 装 Cursor（可选，AI 辅助编程）

如果想用 AI 辅助写代码（跟我配合最好）：

```bash
# 下载 Cursor
# 浏览器访问：https://cursor.sh
# 下载 .dmg，双击安装
# 登录用 GitHub 账号
```

**或者继续用 VS Code**（已经装了），推荐装几个插件：
- **Python**（微软官方）
- **Vue - Official**（Vue 3 支持）
- **Pylance**（Python 智能提示）
- **Continue** 或 **Cline**（AI 辅助，跟我风格类似）

### 1.3 验证

```bash
# 老大已经装好的都跳过
brew --version        # ✅ Homebrew 6.0.12
python3 --version     # ✅ Python 3.13.3（系统版本）
node --version        # ✅ v22.23.1
git --version         # ✅ git version 2.39.5
```

### ⚠️ Python 3.13 vs 3.11

**老大系统是 3.13.3**，跟我们最初计划的 3.11 不同。

**好消息**：3.13 跟 3.11 对我们的栈（FastAPI / SQLModel / Playwright）**完全兼容**。

**两种选择**：

| 选项 | 怎么做 | 推荐度 |
|---|---|---|
| **A 用系统 3.13** | `python3 -m venv venv` | ⭐ 推荐（最省事） |
| B 装 3.11 | `brew install python@3.11` 然后用 `python3.11` | 跟教程完全一致 |

**我建议 A**——用系统 3.13，省得维护多版本。

下面教程**默认用 A 方案**。

---

## 2️⃣ 服务器环境（Ubuntu）

老大服务器"做了初始化"，但要**实际验证**才知道装没装。

去跑 `docs/environment-check.md` 里的 8 条命令（5 分钟），把结果发我。

---

## 3️⃣ 写第一段代码

### 3.1 本地建项目目录

```bash
mkdir -p ~/projects/teacher-question-bank
cd ~/projects/teacher-question-bank
```

### 3.2 用 VS Code / Cursor 打开

```bash
code .  # VS Code
# 或
cursor .  # Cursor
```

### 3.3 新建 main.py

在 VS Code 里新建 `main.py`：

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
        "lesson": "第 1 课：Hello World",
        "python_version": "3.13.3"
    }
```

### 3.4 建虚拟环境 + 装依赖

```bash
# 建虚拟环境（一次性）
cd ~/projects/teacher-question-bank
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
# 激活后终端会显示 (venv) 前缀

# 装 FastAPI 和 uvicorn
pip install fastapi 'uvicorn[standard]'
```

**装包慢的话换国内源**：

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install fastapi 'uvicorn[standard]'
```

### 3.5 跑起来

```bash
uvicorn main:app --reload
```

看到类似输出：

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

**浏览器打开**：
- http://localhost:8000 → 看到 `{"message":"Hello from FastAPI"}`
- http://localhost:8000/api/info → 看到项目信息 JSON
- http://localhost:8000/docs → **FastAPI 自动生成的 API 文档**（超赞！）

✅ 看到这些就算成功！

按 `Ctrl+C` 退出。

---

## 4️⃣ 提交到 GitHub

老大已有仓库 `https://github.com/zj962455-hub/teacher_que_bank`。

### 4.1 准备 .gitignore

在项目根目录新建 `.gitignore`：

```
# Python
venv/
__pycache__/
*.pyc
*.pyo
*.pyd

# 环境变量
.env

# IDE
.vscode/
.idea/
.cursor/

# OS
.DS_Store
Thumbs.db

# 项目特定
uploads/
*.log
```

### 4.2 第一次 commit

```bash
cd ~/projects/teacher-question-bank

git init  # 如果还没 init
git add main.py .gitignore
git commit -m "feat(lesson-01): FastAPI Hello World"

# 关联远程仓库
git remote add origin https://github.com/zj962455-hub/teacher_que_bank.git
git branch -M main
git push -u origin main
```

**如果 push 失败要 token**：
- GitHub 早就不用密码了，需要 Personal Access Token
- 申请：https://github.com/settings/tokens
- 选 `repo` 权限
- 用 token 当密码 push

---

## 5️⃣ 动手做（5-10 分钟任务）

完成下面 3 个小改动，让代码活起来：

### 任务 1：加一个 `/api/lessons` 端点

```python
@app.get("/api/lessons")
def get_lessons():
    return {
        "phase_1": [
            "第 1 课：环境搭建 + Hello World",
            "第 2 课：FastAPI 入门",
            "第 3 课：Vue 3 入门",
            "第 4 课：前后端打通",
            "第 5 课：上传图片",
            "第 6 课：调 Mathpix OCR",
            "第 7 课：KaTeX 渲染公式",
            "第 8 课：存数据库",
            "第 9 课：导出 PDF",
            "第 10 课：部署上线"
        ]
    }
```

### 任务 2：加路径参数

```python
@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int):
    return {
        "id": lesson_id,
        "title": f"第 {lesson_id} 课",
        "duration": "30-60 min"
    }
```

试访问 http://localhost:8000/api/lessons/5

### 任务 3：加点 query 参数

```python
@app.get("/api/greet")
def greet(name: str = "老大", level: int = 1):
    return {
        "message": f"你好 {name}！",
        "level": level,
        "encouragement": "💪" * level
    }
```

试访问：
- http://localhost:8000/api/greet
- http://localhost:8000/api/greet?name=数学老师
- http://localhost:8000/api/greet?name=萝卜特&level=5

完成后访问 http://localhost:8000/docs 看 FastAPI 自动生成的接口文档 —— **这些都是免费的**！

---

## 6️⃣ 提交 + 下次接哪里

```bash
git add main.py
git commit -m "feat(lesson-01): add lessons / greet endpoints"
git push
```

**第 2 课（FastAPI 入门）会做的事**：
- 路由分组（APIRouter）
- 请求体（Pydantic 模型）
- 错误处理
- 异步 async/await
- 项目结构组织（main.py → app/）

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| `python3: command not found` | 重装 Python 或 PATH 没配好 |
| `pip: command not found` | `python3 -m ensurepip --upgrade` |
| `uvicorn: command not found` | 虚拟环境没激活，看终端有没有 `(venv)` 前缀 |
| 端口 8000 被占用 | `uvicorn main:app --reload --port 8001` |
| 浏览器 localhost 打不开 | 检查 uvicorn 终端是否在运行 |
| GitHub push 失败 | 需要 Personal Access Token，不是密码 |
| pip 装包超时 | 换清华源（见 3.4） |

**实在搞不定就截图发我**——我会看截图帮你定位。

---

## ✅ 验收清单

- [ ] 服务器环境验证（environment-check.md 里 5 条命令 OK）
- [ ] 域名 DNS 解析到服务器 IP
- [ ] 本地能跑 `uvicorn main:app --reload`
- [ ] 浏览器访问 http://localhost:8000 看到 Hello
- [ ] 浏览器访问 http://localhost:8000/docs 看到 API 文档
- [ ] 完成了 3 个「动手做」任务
- [ ] 代码已 push 到 `zj962455-hub/teacher_que_bank`
- [ ] 把 GitHub 仓库链接 + 截图发我

**完成后告诉我，我们开始第 2 课** 🚀
