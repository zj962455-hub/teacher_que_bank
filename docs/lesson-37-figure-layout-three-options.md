# 题图排版三选项 + 编辑保存落库 — lesson-37

## 起因（老大 2026-11-09 19:46）

两条需求：

1. **题库界面 → 题目 → 编辑 → 保存，改动没保存**（账号登录状态正常）
2. **题图摆放位置只给老师三个选项**：题目文字下方右下角 / 题目文字下方左下角 / 不显示题图

## 需求 1 根因：编辑器把「原题内容」发回去了

`QuestionEditor.vue` 的 `saveToDatabase()` 里：

```js
content_plain: buildPlainText.value,
content_markdown: props.withFormulas || content.value,   // ← 元凶
```

`props.withFormulas` 是**进编辑器时那版原题**的 Markdown，不是老师改完的内容。
`props.withFormulas` 永远非空 → 老师改的字被原值覆盖 → 界面提示「已保存到题库」，
库里却纹丝不动。`content_plain` 同理：`buildPlainText` 是按 **blocks**（OCR 原文）重算的，
blocks 永远不变，改动同样被盖回去。

线上无头复现（`lesson-03/scripts/verify-question-edit.cjs`）：

- PUT 请求体 `content_markdown` **不含**新加的标记
- 响应 200，库里也没有 → 确认是「发了旧值」，不是接口报错、不是登录态问题

## 修法

### 前端

- `content_markdown` 改发 `content.value`（老师改过的正文）
- 不再发 `content_plain`（由后端按改后正文重算，避免两套算法打架）
- `copyJson` 里的 `contentMarkdown` 同步改成 `content.value`

### 后端

- `math_parser.py` 新增 `markdown_to_plain()`：把带 `$...$` 的 Markdown 转纯文本
（公式段走 `latex_to_plain`，文字原样保留）
- `routers/questions.py` 的 PUT：
  - 带 `blocks` 的更新（OCR 一键入库路径）→ 三个版本仍由 blocks 推导，**不变**
  - 只带 `content_markdown` 的更新（老师编辑路径）→ `content_plain` 按改后正文重算

## 需求 2：版式收敛为三项

| 版式 | 效果 |
|---|---|
| `bottom_right` | 题目文字下方·右下角（默认） |
| `bottom_left` | 题目文字下方·左下角 |
| `none` | 不显示题图 |

- 后端白名单 `FIGURE_LAYOUTS` 收敛为三项，非法值回落 `bottom_right`
- 迁移 `011_figure_layout_three_options.sql`：旧值（`right` / `bottom_center`）统一回落默认
- 前端 `QuestionEditor.vue` 下拉只剩三项；`QuestionDetailPage.vue` / `PaperEditor.vue` /
  `paper_pdf.html` 的 CSS 同步改成「图在文字下方」（block 布局 + 左/右对齐）

## 验收

- 后端全量：`276 passed`（新增 `tests/test_question_edit_save.py` 3 条 + 更新 `test_figure_layout.py`）
- 线上无头（`verify-question-edit.cjs`，test2 账号）：
  - 下拉选项 = `["题目文字下方·右下角（默认）","题目文字下方·左下角","不显示题图"]`
  - PUT 载荷含新标记 ✓、响应含新标记 ✓、刷新后库里含新标记 ✓、纯文本版同步 ✓
  - 验收标记已用 API 还原（内容回到原样）
- 真实导出（test2 账号「题图排版验收卷」卷 id=3 → export.jpg → 第 1 页 JPG）：
  图在题干文字**下方靠右** ✓

## 提交

`2410c6a fix(lesson-37): 编辑保存真的落库 + 题图排版收敛为三选项`（已推 origin/main）

## 遗留

- 导出的正文里还留着 `【题图】` 占位符（lesson-36 给 figure block 加的），
  是给「复制纯文本」用的；导出 PDF 时它也在。要不要导出时去掉，等老大一句话。
