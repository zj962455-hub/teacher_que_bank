# 题图排版（figure_layout / figure_width）— lesson-36

## 起因

老师反馈：**「按排版美化来说，题图放到题目右下方比较合适」**，并希望
「支持老师自定义格式」。

排版是**每道题自己的诉求**：有的题图大、有的图小，有的老师习惯图在右下
（教材式：文字在左、图在右下），有的习惯图在下方居中，还有的根本不想让
图进卷子。所以版式不能写死在导出模板里 —— 要存到题上。

## 数据

迁移 `010_add_figure_layout.sql`：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `figure_layout` | VARCHAR(20) | `'bottom_right'` | 版式：bottom_right / right / bottom_left / bottom_center / none |
| `figure_width` | INTEGER | `0` | 题图宽度占题目宽度百分比，0 = 用该版式默认宽度 |

老题迁移后是 `bottom_right` —— 也就是说**所有带图的旧题，导出时排版会
变成右下角**（这正是老师要的效果）。不想要的题在题目编辑器里改回来即可。

## 版式含义

| 版式 | 效果 | 默认宽度 |
|---|---|---|
| `bottom_right` | 文字在左、题图在右下（教材式） | 38% |
| `right` | 题图在右侧，与文字顶部对齐 | 32% |
| `bottom_left` | 题图在下方靠左（旧版排版） | 72% |
| `bottom_center` | 题图在下方居中 | 60% |
| `none` | 不显示题图 | — |

## 改动点

- `models.py`：Question 加两个字段
- `routers/questions.py`：
  - `_normalize_figure_layout` / `_normalize_figure_width`（白名单 + 夹紧，脏值回落默认）
  - 新建 / 从 OCR 一键入库 / 更新 三条路径都收这两个字段
  - `_to_dict` 回传
- `routers/papers.py`：试卷详情与导出（PDF / JPG）带上版式和宽度
- `templates/paper_pdf.html`：题干与图包进 `.q-body` flex 容器，按版式换 class；
  每种版式一套默认宽度（内联 `width` 可覆盖）
- 前端：
  - `QuestionEditor.vue`：**题图排版**下拉 + **宽度**输入（老师自己定）
  - `OcrResult.vue`：校对页改的版式随「一键入库」一起提交
  - `QuestionDetailPage.vue`：详情页按同一套版式渲染，所见即所得

## 验收

- 单测 `lesson-02/tests/test_figure_layout.py`（6 条）：规范化 + 模板输出
- 线上真实导出（test2，卷「题图排版验收卷」）：四种版式各导一次 JPG，逐张看图确认
  - bottom_center → 图在下方居中 ✓
  - right → 图在右侧顶部对齐 ✓
  - none → 不出图 ✓
  - bottom_right + width=30 → 图在右下且宽度 30% ✓
