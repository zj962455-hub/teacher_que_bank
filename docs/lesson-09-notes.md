# Lesson 09 精简注释版 · 组卷 + 导出 PDF

> 上一课:题目存进 PostgreSQL(SQLModel)。
> 这一课:**组卷 + 导出 PDF** —— 老师挑题、排顺序、改题号,一键出带公式的 A4 卷子。

---

## 📍 Phase 1 最后一课

按 `learning-path.md`,Phase 1 目标:
> 「上传图片 → OCR → 显示 + **存库** + **导出 PDF**」

前 8 课把前半段做完了,这一课补最后一段。做完 Phase 1 就闭环 —— **能 demo 给老师看**。

---

## 🧠 3 个核心概念（读 3 分钟）

### 1. PDF 怎么生成?—— Playwright 打印 HTML

PDF 的本质是「排版好的页面」。三种常见方案:

| 方案 | 优点 | 缺点 |
|---|---|---|
| reportlab / fpdf 直接画 | 快 | 公式、表格排版极难做 |
| LaTeX 编译 | 公式最漂亮 | 要装 TeX,中文麻烦 |
| **Playwright 打印 HTML** | **所见即所得,前端效果直接搬** | 要启浏览器(稍慢) |

**关键洞察:我们已经有前端了,为什么要重新实现一遍排版?**
把题干塞进 HTML → 让浏览器渲染 → 打印成 PDF。**PDF 效果跟网页预览完全一致**。

decisions.md 早就锁了 `PDF | Playwright（Python 版）| 渲染 KaTeX 公式`。

### 2. 公式渲染发生在哪?—— 后端不需要 KaTeX

后端是 Python,没有 KaTeX。但**这不重要**:

```
后端: 生成 HTML(题干是 $...$ 标记)  →  写临时文件
Chromium: 加载 HTML → KaTeX auto-render 扫描 $...$ → 替换成公式 HTML
Playwright: 等渲染完 → 打印 PDF
```

后端只负责「把文字传过去」,公式排版交给浏览器引擎 —— **跟前端看到的效果完全一致**。

**KaTeX auto-render 的关键 API:**
```js
renderMathInElement(document.body, {
  delimiters: [
    { left: "$$", right: "$$", display: true },   // 块级
    { left: "$",  right: "$",  display: false },   // 行内
  ],
  throwOnError: false,   // 公式语法错时显示原文,不炸整页
});
```

### 3. 试卷为什么要单独的关联表?

```
papers (试卷)                    paper_questions (关联)
├─ id                          ├─ id
├─ title      ← 老师自定义      ├─ paper_id    → papers.id
├─ subtitle   ← 老师自定义      ├─ question_id → questions.id
└─ created_at                   ├─ order_index ← 排序
                                ├─ label       ← 自定义题号「一、」「(1)」
                                └─ score       ← 分值
```

**为什么不把 id 列表直接存成 JSON?**
1. **顺序** —— 存 list 改一次顺序要整个更新
2. **自定义题号** —— 老师可能想要「一、」「(1)」「第一题」不同格式
3. **分值** —— 组卷常见需求

---

## 🧭 3 个设计决策（老大拍板）

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | KaTeX 资源 | **本地静态资源** | 部署到 ECS 不依赖外网,公式不会渲染失败 |
| 2 | 导出粒度 | **多题 PDF(组卷效果)** | 目标就是组卷 |
| 3 | PDF 内容 | **只放题干+公式(不放原图)** | 干净的卷面;防 OCR 认错靠「组卷时在线修改」 |

**老大还追加了两个需求:**
- 试卷要**保存**(不是临时导出)→ 加 `papers` 表
- **题号、标题都要支持老师自定义修改**

---

## 📁 本课最终改动

```
teacher_que_bank/
├── lesson-02/
│   ├── app/
│   │   ├── models.py                    ← 改:加 Paper + PaperQuestion 模型
│   │   ├── main.py                      ← 改:接 papers 路由 + 挂 /static
│   │   ├── routers/papers.py            ← 新增:8 个端点(试卷 CRUD + 导出)
│   │   ├── services/pdf_export.py       ← 新增:Jinja2 模板 + Playwright 渲染
│   │   └── templates/paper_pdf.html     ← 新增:PDF 模板(含 KaTeX + 排版)
│   └── static/katex/                    ← 新增:KaTeX 静态资源(596KB)
└── lesson-03/
    ├── src/api/papers.js                ← 新增:试卷 API 客户端
    ├── src/components/PaperEditor.vue   ← 新增:组卷界面
    ├── src/components/QuestionEditor.vue ← 改:加 mode='edit' 支持保存到题库
    ├── src/components/QuestionBank.vue  ← 改:加「编辑」按钮
    └── src/App.vue                      ← 改:接入组卷 + 题目编辑
```

---

## 🚀 步骤

### 步骤 1: 装 Playwright

```bash
pip install playwright jinja2
playwright install chromium
```

⚠️ **国内下载慢/失败** —— 用 npmmirror 镜像:
```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright playwright install chromium
```
（实测官方源下了一小时没落盘，换镜像几十秒完成）

### 步骤 2: 复制 KaTeX 静态资源

```bash
mkdir -p lesson-02/static/katex/fonts
cp lesson-03/node_modules/katex/dist/katex.min.css lesson-02/static/katex/
cp lesson-03/node_modules/katex/dist/katex.min.js lesson-02/static/katex/
cp lesson-03/node_modules/katex/dist/contrib/auto-render.min.js lesson-02/static/katex/
cp lesson-03/node_modules/katex/dist/fonts/*.woff2 lesson-02/static/katex/fonts/
```
**只拷 woff2 就够** —— CSS 里 `url(fonts/xxx.woff2)` 排在 woff/ttf 前面，浏览器取第一个就命中。

### 步骤 3: 数据模型

```python
class Paper(SQLModel, table=True):
    title: str = Field(default="未命名试卷", max_length=200)
    subtitle: str = Field(default="", max_length=200)   # 姓名/班级/日期
    questions: list["PaperQuestion"] = Relationship(back_populates="paper", cascade_delete=True)

class PaperQuestion(SQLModel, table=True):
    paper_id: int = Field(foreign_key="papers.id", index=True)
    question_id: int = Field(foreign_key="questions.id", index=True)
    order_index: int = Field(default=0)
    label: str = Field(default="", max_length=50)    # 自定义题号,空则自动
    score: float = Field(default=0.0)
```

### 步骤 4: PDF 服务（关键在 file:// 而非 HTTP）

```python
# 临时 HTML 写在 static/ 下 → 跟 katex/ 同级,相对路径能解析
tmp_path = STATIC_DIR / f"_pdf_{uuid.uuid4().hex}.html"
tmp_path.write_text(html, encoding="utf-8")

page.goto(f"file://{tmp_path.resolve()}", wait_until="load")
page.wait_for_function("window.__katexDone === true", timeout=10000)
pdf_bytes = page.pdf(format="A4", print_background=True, margin={...})
```

**为什么不用 HTTP 拿 katex?**
如果模板里引 `http://127.0.0.1:8000/static/katex/...`,
Chromium 会反过来请求 FastAPI —— 而生成 PDF 的请求正占着这个服务。
单 worker 时**死锁**(事件循环被同步的 Playwright 阻塞)。

用 `file://` 完全避开:临时文件跟 `static/katex/` 同级,相对路径直接解析到字体。

### 步骤 5: 模板的 KaTeX 渲染完成标志

```html
<script>
  renderMathInElement(document.body, { delimiters: [...] });
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      window.__katexDone = true;   // Playwright 侧等这个
    });
  });
</script>
```
**双层 rAF** —— 等一帧确保 KaTeX 的 DOM 替换完成,再设标志。

---

## 🛡️ 安全

| 风险 | 防护 |
|---|---|
| 题干里的 `<script>` | Jinja2 `autoescape=True` 自动转义成 `&lt;script&gt;` |
| 题干里的 `$` 被当公式 | KaTeX `throwOnError: false` + `errorColor` 标红不炸页 |
| PDF 文件名中文 | RFC 5987 `filename*=UTF-8''{quote(name)}` |
| 临时 HTML 残留 | `finally` 里 `unlink(missing_ok=True)` |

---

## ⚠️ 踩过的坑

### 坑 1: Chromium 下载
```
官方源下了一小时没落盘 → 换 npmmirror 镜像几十秒完成
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
```

### 坑 2: useMessage 又双叒叕
lesson-07 结论:统一用 `discreteApi`(不需要 Provider)。
这一课写 PaperEditor 时又写了 `useMessage()` → 运行时白屏。
**教训:新组件第一行 import 前先 grep 项目里的现成用法。**

### 坑 3: naive-ui 没有 `DataTable`
导出名是 `NDataTable`,而且这里根本用不到(我用了 NList)。

### 坑 4: h() 的 props 用 innerHTML 不是 v-html
（lesson-08 踩过,这一课写表格时又差点踩）

---

## 📚 速查表

### 端点一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | /api/papers/ | 试卷列表 |
| POST | /api/papers/ | 新建试卷 |
| GET | /api/papers/{id} | 详情(含题目+题号) |
| PUT | /api/papers/{id} | 改标题/副标题 |
| DELETE | /api/papers/{id} | 删除试卷 |
| POST | /api/papers/{id}/questions | 加题 |
| PUT | /api/papers/{id}/questions/{pq_id} | 改题号/分值/顺序 |
| DELETE | /api/papers/{id}/questions/{pq_id} | 移除题 |
| GET | /api/papers/{id}/export.pdf | 导出 PDF |

### Playwright 打印 PDF 常用参数

```python
page.pdf(
    format="A4",
    print_background=True,        # 保留背景色(有些公式需要)
    margin={"top":"18mm","bottom":"18mm","left":"16mm","right":"16mm"},
)
```

### CSS 里防止题目被分页切开

```css
.question {
    page-break-inside: avoid;   /* 题目不要被切成两半 */
    break-inside: avoid;
}
.katex-display {
    page-break-inside: avoid;   /* 公式同理 */
}
```

### 中文题号自动生成

```python
CN_NUMBERS = ["一","二","三",...,"十","十一",...]
def auto_label(index):
    if 0 <= index < len(CN_NUMBERS):
        return f"{CN_NUMBERS[index]}、"
    return f"{index + 1}."
```

---

## 🎓 Phase 1 收官

| 课 | 主题 | 状态 |
|---|---|---|
| 1 | 环境搭建 + Hello World | ✅ |
| 2 | FastAPI 入门 | ✅ |
| 3 | Vue 3 入门 | ✅ |
| 4 | 前后端打通 | ✅ |
| 5 | 上传图片 | ✅ |
| 6 | 调 PaddleOCR OCR | ✅ |
| 7 | KaTeX 渲染公式 | ✅ |
| 8 | 存数据库 | ✅ |
| 9 | 组卷 + 导出 PDF | ✅ |
| 10 | 部署上线 | ⏳ 下一课 |

**现在的完整链路:**
```
上传图片 → PaddleOCR 识别(文字+公式) → KaTeX 渲染 → 存题库
    → 自动分类(学科/题型/学段/难度) → 人工修正 → 组卷(排序/题号/分值)
        → 导出 PDF(A4 · 公式漂亮 · 中文题号)
```

**这就是能 demo 给老师看的东西了。**

下一课 lesson-10: Nginx + systemd + 域名,把这套东西放到公网上。

---

## 🔗 相关文件

- 进度:`../docs/learning-path.md` · 决策:`../docs/decisions.md`
- 上一课:`lesson-08-notes.md`(SQLModel 存题目)
- 后端:`lesson-02/app/{models.py,database.py,routers/papers.py,services/pdf_export.py}`
- 模板:`lesson-02/app/templates/paper_pdf.html`
- 前端:`lesson-03/src/{api/papers.js,components/PaperEditor.vue}`
