# 【题图】占位符：导出时去掉 + 老师可手动删除 — lesson-38

## 起因（老大 2026-11-09）

「导出时去掉，同时支持老师手动修改去掉」

上一课（lesson-37）留的尾巴：导出的正文里还留着 `【题图】` 占位符
（lesson-36 给 figure block 加的），是给「复制纯文本」用的；导出 PDF 时它也在。

## 为什么占位符是噪音

- 卷子上**明明有图**（figure_path 那张单独带进 PDF/JPG）
- 正文里再写一遍「【题图】」= 同一件事说两遍
- 而且它是系统内部标记，老师不该在自己的卷子上看到

## 方案：输出时过滤 + 存储层保留

关键取舍：**自动过滤不许改写老师存的内容**。

| 层 | 行为 | 理由 |
|---|---|---|
| 存储层（DB） | 保留 `【题图】` | 只有老师主动编辑才能改存储；系统不许偷偷动 |
| 导出（PDF/JPG/Excel/备份） | 去掉 | 给老师看的成品，不带内部标记 |
| 页面展示（详情/列表/仪表盘/组卷/分享） | 去掉 | 同上 |
| 编辑器输入框 | **保留** | 老师要能看见它、才能手动删掉它 |

老师手动删掉 → 保存 → 永久生效，刷新不复活（DB 里真没了）。

## 后端

### `app/services/classifier.py`

新增 `FIGURE_PLACEHOLDER = "【题图】"` 和 `strip_figure_placeholder(text)`：

- 整行只有占位符 → 整行丢掉
- 同行还混着文字 → 只去掉占位符，保留这行
- 删完连续空行 → 收成最多两个换行

`build_content_versions()` 改用常量拼占位符（行为不变）。

### 接入点

| 文件 | 位置 | 口径 |
|---|---|---|
| `routers/papers.py` | `_export_items()` | 试卷 PDF + JPG（两条链路同一份口径） |
| `routers/shares.py` | `_export_items()` | 分享链接 PDF + JPG |
| `routers/questions.py` | `/export/excel` | 题库 Excel |
| `routers/questions.py` | `/export/backup` | JSON 备份（figure 信息在 blocks_json 里，不丢东西） |

### 顺带修的一个同类 bug

`QuestionEditor.vue` 的三种复制：

```
copyPlain()   → buildPlainText.value || content.value   // ❌ buildPlainText 按 blocks（OCR 原文）算
copyFormula() → props.withFormulas || content.value       // ❌ 进编辑器时那版原题
copyJson()    → content: buildPlainText.value             // ❌ 同上
```

老师删掉的【题图】会从 blocks 里复活，老师改的字也会丢。
改成按 `content.value`（老师改过的正文）算，公式转 Unicode 走前端本地
`markdownToPlain()`（与后端 `markdown_to_plain()` 等价）。

## 前端

新增 `lesson-03/src/utils/figurePlaceholder.js`：`stripFigurePlaceholder(text)`
（与后端同名函数同口径）。

接入展示点（7 处）：

- `pages/QuestionDetailPage.vue`
- `pages/QuestionsPage.vue`
- `pages/DashboardPage.vue`
- `pages/PaperExportPage.vue`
- `pages/SharedPaperPage.vue`
- `components/QuestionBank.vue`
- `components/PaperEditor.vue`（题目列表 + 组卷预览）

**`components/QuestionEditor.vue` 故意不接** —— 编辑器输入框要留着占位符，老师才能删。

## 验收

### 后端

- 新增 `lesson-02/tests/test_figure_placeholder.py`（13 条）
- 全量：**289 passed**

锁住的行为：

1. `strip_figure_placeholder()` 三种形态（整行 / 同行 / 连续空行）
2. OCR 建题时占位符照旧写进存储（占位符本身还得有用）
3. 试卷导出、分享导出、Excel 导出 —— 输出都不带占位符
4. **自动过滤不碰数据库**（导出完再查，库里占位符还在）
5. 老师手动删掉 → 保存 → 真没了，刷新不复活
6. 老师只改别的字段（难度）→ 占位符还在存储里

### 线上（test2 账号，题 id=28 / 卷 id=3「题图排版验收卷」）

| 检查 | 结果 |
|---|---|
| GET 题详情（存储层） | markdown / plain 都**含**占位符 ✓（自动过滤没改库） |
| 题库 Excel 导出 | 15 行，**0** 个单元格带占位符 ✓ |
| 卷 PDF / JPG 导出 | 200，PDF 106 KB / ZIP 45 KB ✓ |
| 老师手动删占位符 → PUT | 200 ✓ |
| 刷新再 GET | 占位符**没复活**（markdown/plain 都不含）✓ |
| 删除后再导出 Excel | 0 个带占位符 ✓ |
| 还原 | 按快照逐字节回写，DB 与快照**完全一致** ✓ |

## 坑

- **psql 输出别直接 split 逗号/竖线**：正文里有换行和 `\t`，用
  `encode(convert_to(...,'UTF8'),'base64')` 拿，回本地再解码比对
- **线上验收必须自己还原**：先快照 → 改 → 验证 → 按快照回写，
  不然会在老师账号里留测试数据
- psql `-f` 读文件时 postgres 用户读不了 root 写的文件 → 先 `chmod 644`

## 提交

`fix(lesson-38): 导出去掉【题图】占位符 + 老师可手动删除`
