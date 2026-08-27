# 已确认决策（不要再反复问）

> 老大 2026-08-13 21:49 拍板
> 任何调整前先看这里

---

## 🛠 技术栈（已锁定）

| 层 | 选 | 理由 |
|---|---|---|
| 前端 | **Vue 3 + Vite + naive UI ★ 2026-08-27 拍板** | 中文社区活跃 · 组件库齐 · 暗色主题原生支持 |
| UI 组件 | **naive UI (^2.45.2)** + vfonts | Vue 3 原生 TS 组件库 · 表格 / 表单 / 上传 / 树 / 主题切换 全有 |
| CSS | scoped CSS（原生） + Tailwind utility class（可选） | lesson-03/05 原生 CSS 已收工不重构；新增组件用 naive UI 风格 + scoped |
| 后端 | **Python 3.11+ FastAPI + SQLModel** | 老大自学 Python |
| 数据库 | PostgreSQL 15 | 结构化数据主流 |
| 小程序 | uni-app | 一码多端 |
| 部署 | gunicorn + systemd + Nginx | Python 标准方案 |
| OCR | **自托管 PaddleOCR (PP-StructureV3)** ★ 2026-08-26 拍板 | ECS `https://lanhu-lab.top` · 零 SaaS 依赖 · 部署见 `deploy/paddleocr/` |
| 公式 | KaTeX | 已锁 |
| PDF | Playwright（Python 版） | 渲染 KaTeX 公式 |
| 代码 | Git + GitHub | 仓库名 `teacher_que_bank` |
| IDE | VS Code（已装）/ Cursor 可选 | 老大本地有 VS Code |

---

## 🎨 前端 UI 方案（2026-08-27 拍板 · 老大学习时同时敲定）

**决策：lesson-06 起正式用 naive UI 做组件库。**

### 为什么选 naive UI
- Vue 3 + TypeScript 原生（16k+ GitHub star · 涂森 tusen-ai 出品）
- 70+ 组件：NDataTable（虚拟滚动 + 列固定）/ NForm / NUpload / NTree / NSelect / NPopconfirm / NConfigProvider 暗色主题
- 中文文档原生
- 按需引入 · tree-shaking · 比 Element Plus 轻
- 暗色模式原生支持（CSS variables）—— 未来给学生用做"夜间模式"零成本

### 验证记录（2026-08-27）
- `lesson-03/src/components/NaiveUIDemo.vue`：5 个 Card（暗色开关 / 基础控件 / DataTable 搜索筛选分页 / Form 校验 / 图片上传接 lesson-05 后端）
- `vite build` 通过（2719 modules · 571ms）
- puppeteer 截图亮色 + 暗色均正常
- 0 控制台错误

### 一个踩过的坑（写代码时记住）
`useMessage()` 在 setup 顶层同步调用，但 NMessageProvider 是子组件（还没 mount）→ inject 拿 null → 抛错 → 整个 App 挂掉。

**修复：** 用 `createDiscreteApi(['message'])` 替代 `useMessage()`，独立 API，不依赖 Provider 树时序。

### lesson 划分
- lesson-03（已收工，scoped CSS 风格）—— 不重构，保持现状
- lesson-05（已收工，UploadImage）—— 不重构
- **lesson-06 起** —— 新增组件全部用 naive UI，按需引入
- lesson-31（UI 美化）—— 直接用 naive UI 主题系统，不再单独搞 Tailwind 设计稿

### Tailwind 怎么处理
- 不强制装（lesson-03 当前没装）
- 如果新组件需要局部 layout 微调（`flex` / `gap-4`）→ 单独加，不全局引入
- 避免"两套样式系统打架"

---

## 💻 资源（已确认）

| 项 | 值 |
|---|---|
| 域名 | **lanhu-lab.top** |
| 服务器 | 阿里云 2C4G |
| 服务器系统 | Ubuntu（已初始化） |
| 本地开发机 | Mac mini |
| 代码仓库 | https://github.com/zj962455-hub/teacher_que_bank |
| 项目目录 | `~/projects/teacher-question-bank` |

---

## 👥 用户规模

- **MVP 阶段**：个位数老师
- **50 个老师** → PaddleOCR 服务（PP-StructureV3 · 单进程 2 并发 ·够用；上量后加 worker /换 GPU）
- 月成本估算 ¥0（OCR）（已有 ECS 2C4G 负担，不再有 SaaS 费用）

---

## 📚 学习方式（已确认）

- **老大写代码**，**我辅助**（review + 解释 + 写样板代码 + debug）
- **节奏**：晚上 + 周末，**不固定时间**
- **路径**：5 个阶段 / 35 节课
- **当前**：第 0 阶段（产品方向）✅ → **第 1 课（环境搭建 + Hello World）** ⬅ 下一步

---

## 🎯 产品核心（来自原型 v0.2）

- 教培数学老师 **私人题库 + 轻量组卷**
- 核心卖点：**图片 OCR + 公式自动识别**（差异化于组卷网/学科网）—— 由自托管 PaddleOCR 提供
- 题目类型：选择/填空/解答
- 存储：题干文字（HTML）+ 公式（LaTeX）+ 配图（原图保留）
- 导出：PDF / JPG
- 商业模式：MVP 免费，跑通用户量后再加付费墙（¥99-199/年）

---

## 🔒 合规（已确认）

- 几乎不涉及个人敏感数据
- 题目是老师的教研成果（不算个保法里的"个人信息"）
- 手机号只是登录账号
- **不需要虚拟号 / 第三方数据源 / 业主授权那一套**
- 但仍需：用户协议 + 隐私政策 + cookie 提示（个保法第 17 条）

---

## ❓ 仍待决策（暂不急）

- 商业模式（什么时候加付费墙）→ Phase 5 再说
- 服务器访问凭证（老大 SSH 上来才能我远程装环境）→ 后面给方案
- 高保真 UI 设计稿 → MVP 跑通后再说
- 小程序上线审核材料 → Phase 4 再说
