# Lesson 08 精简注释版 · 存数据库（PostgreSQL + SQLModel）

> 上一课:公式能渲染、题目能编辑、组卷能出 PDF。
> 这一课:**题目真正存进数据库** —— 之前全靠 JSON 文件,重启就丢、没法多条件查询、没法组卷复用。

---

## 📍 为什么必须有数据库

| 之前(lesson-06/07) | 现在 |
|---|---|
| `uploads/ocr/{task_id}.json` 一个任务一个文件 | 一张 `questions` 表 |
| 查「所有数学题」要 grep 整个目录 | `WHERE subject='数学'` |
| 组卷要手工挑 task_id | `questions.id` 直接选 |
| 分类/难度是前端算的,不入库 | 存字段,可排序可筛选 |
| 改个字段要改 JSON 再同步 | `UPDATE` 一条记录 |

---

## 🧠 4 个核心概念（读 4 分钟）

### 1. SQLModel = SQLAlchemy + Pydantic 融合

FastAPI 作者写的。好处:**一个类同时是数据库模型和 API 请求/响应模型**。

```python
class Question(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subject: str = Field(default="未知", index=True)
```

`table=True` → 是数据库表；不写 → 只是 Pydantic 模型(用于请求体校验)。

### 2. 三个内容版本并存(lesson-07 的成果直接用)

| 字段 | 内容 | 用途 |
|---|---|---|
| `content_plain` | 公式用 Unicode（x²） | 复制到 Word |
| `content_markdown` | 公式用 `$...$` | 二次编辑、KaTeX 渲染 |
| `blocks_json` | 完整 OCR blocks | 重新渲染、看 bbox |

**为什么不拆三张表**:MVP 阶段数据量小(几千题),单表查询简单。拆表要处理顺序/引用,收益不大。**等 lesson-11+ 做标签/组卷再拆。**

### 3. 依赖注入拿数据库会话

```python
# app/database.py
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

# app/routers/questions.py
@router.get("/")
def list_questions(session: Session = Depends(get_session)):
    ...
```

**每个请求一个会话,函数结束自动关闭。** 不在路由里手写 `Session(engine)`。

### 4. 分类器要在后端也有一份

lesson-06 任务 5C 的分类器是**前端 JS**。但 `from-ocr` 端点要后端自己分类,所以 Python 侧要有同规则的一份。

**规则必须完全一致** —— 9 个用例实测对齐:
```python
SUBJECT_RULES = [
    {"subject": "物理", "keywords": ["加速度", "电流", "电压", ...]},   # 特征词在前
    {"subject": "数学", "keywords": ["方程", "函数", ..., "求"]},       # 泛词兜底
]
```
⚠️ **顺序很重要**:泛词('求'/'已知')放前面会把物理题误判成数学。

---

## 🧭 2 个设计决策（老大拍板）

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | 建表方式 | `create_all()` | MVP 不学 Alembic;lesson-10 部署时再补 |
| 2 | 库/表命名 | `teacher_question_bank.questions` | 跟项目名一致,避免重名 |

---

## 📁 本课最终改动

```
teacher_que_bank/
├── lesson-02/
│   ├── app/
│   │   ├── database.py              ← 新增:engine + get_session
│   │   ├── models.py                ← 新增:Question 模型 + create_tables()
│   │   ├── routers/questions.py      ← 新增:6 个 CRUD 端点
│   │   └── services/classifier.py    ← 新增:Python 版分类器
│   └── main.py                      ← 改:挂路由 + startup 建表
```

---

## 🚀 步骤

### 步骤 1: 装依赖

```bash
pip install sqlmodel 'psycopg[binary]'
```

### 步骤 2: 数据库连接

```python
# app/database.py
DATABASE_URL = os.getenv("DATABASE_URL")   # ⚠️ 必填,不给默认值
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 未配置!")

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
```

⚠️ **别写死 fallback**(本地开发地址)。生产 EnvironmentFile 没生效时会**静默连到错误的库**,
报错还难查("Ident authentication failed for user rrobot" —— 连的是 Mac 的用户)。

### 步骤 3: 数据模型

```python
class Question(SQLModel, table=True):
    __tablename__ = "questions"
    id: Optional[int] = Field(default=None, primary_key=True)
    subject: str = Field(default="未知", index=True, max_length=20)
    question_type: str = Field(default="未知", index=True, max_length=20)
    grade: str = Field(default="通用", index=True, max_length=20)
    difficulty: str = Field(default="简单", index=True, max_length=20)
    content_plain: str = Field(default="", max_length=10000)
    content_markdown: str = Field(default="", max_length=10000)
    blocks_json: str = Field(default="", max_length=50000)
    image_path: str = Field(default="", max_length=500)
    ocr_task_id: str = Field(default="", index=True, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

⚠️ **`question_type` 不是 `type`** —— `type` 是 Python 内建名,容易跟 SQLModel 元信息混淆。

⚠️ **时间戳必须带时区**。字段是 `TIMESTAMP WITH TIME ZONE`,
`datetime.now()` 是 naive 的 → 报 `Datetime values must have timezone information`。
用 `datetime.now(timezone.utc)`。

### 步骤 4: 建表

```python
def create_tables() -> None:
    SQLModel.metadata.create_all(engine)
```
main.py 里挂 startup 钩子:
```python
@app.on_event("startup")
def on_startup():
    create_tables()
```

### 步骤 5: CRUD 端点

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/questions/` | 新建 |
| GET | `/api/questions/` | 列表(学科/题型/学段/难度筛选 + 关键词 + 分页) |
| GET | `/api/questions/{id}` | 详情 |
| PUT | `/api/questions/{id}` | 更新(blocks 变了自动重算三版本) |
| DELETE | `/api/questions/{id}` | 删除 |
| POST | `/api/questions/from-ocr/{task_id}` | **从 OCR 结果一键入库** |

**from-ocr 是这一课最有价值的端点**:
```python
record = TASKS.get(task_id)          # 从 ocr_store 读
blocks = record["result"]["blocks"]
versions = build_content_versions(blocks)   # 生成三版本
auto = classify_blocks(blocks)              # 自动分类
```
老师 OCR 完点一下就入库,**不用前端再传一遍数据**。

---

## ⚠️ 踩过的坑

### 坑 1: 时区
```
sqlalchemy.exc.OperationalError: Datetime values must have timezone information
```
`datetime.now()` → `datetime.now(timezone.utc)`。**所有带时区的字段都要用 aware datetime。**

### 坑 2: fallback 连错库
代码写死 `postgresql+psycopg://rrobot@localhost:5432/...` 作为默认值。
生产环境变量没生效时**静默用本地地址** → 连到 Mac 的库 → 认证失败,报错完全指错方向。
**修:必填,缺失就启动报错。**

### 坑 3: 分类规则顺序
第一版数学排第一,关键词含 '求' → 「质量2kg,求加速度」被判成数学。
**特征强的词(加速度/摩尔/光合作用)必须排前面,泛词(求/已知)兜底。**

### 坑 4: psql 连不上
Homebrew PostgreSQL 默认用当前 OS 用户,没有 `postgres` 角色:
```
psql -U postgres → FATAL: role "postgres" does not exist
```
用 `psql -d postgres` 或 `su - postgres -c "psql ..."` 连。

---

## 📚 速查表

### SQLModel 常用

```python
from sqlmodel import Field, SQLModel, Session, select
from typing import Optional

# 查询
stmt = select(Question).where(Question.subject == "数学")
items = session.exec(stmt).all()

# 计数
count = len(session.exec(select(Question)).all())

# 新增
session.add(Question(subject="数学", content_plain="..."))
session.commit()
session.refresh(question)     # 拿回自增 id

# 更新
question = session.get(Question, 1)
question.difficulty = "困难"
session.add(question)         # ⚠️ SQLModel 要显式 add
session.commit()

# 删除
session.delete(question)
session.commit()
```

### 数据库连接串格式

```
postgresql+psycopg://用户名:密码@主机:端口/库名
```

---

## 🔗 相关

- 上一课:`lesson-07-notes.md`(KaTeX + 公式编辑)
- 下一课:`lesson-09-notes.md`(组卷 + PDF)
- 部署:`lesson-10-notes.md`
