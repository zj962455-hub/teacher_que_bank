# Lesson 03 精简注释版 · Vue 3 入门

> 在 FastAPI 后端基础上,**学 4 件大事**:
> 1. 单文件组件(.vue = template + script + style)
> 2. 响应式数据(ref / reactive)
> 3. 模板语法({{ }} / v-bind / v-on / v-model)
> 4. 列表渲染(v-for + :key)
>
> 这一课比 lesson-02 重要——前端所有课都用这套结构。

---

## 🧠 4 个核心概念(读 1 分钟)

### 1. 单文件组件 — `.vue` 三件套

**为什么**: Vue 把 HTML/JS/CSS 塞一个文件,组件化复用 + scoped 样式不污染。

**类比**: `LessonList.vue` ≈ FastAPI 的 `app/routers/questions.py`——一个文件管一块业务。

### 2. 响应式数据 — ref / reactive

**为什么**: 数据改了 → 页面自动更新,不用手动 `document.getElementById(...)`。

**类比**: ref ≈ FastAPI 的 `return {"data": ...}`——把数据"塞"到 UI,UI 跟着数据走。

**关键**: script 里访问 ref 用 `.value`,template 里自动 unwrap(不用 .value)。

### 3. 模板语法 — 4 个常用

**为什么**: 把数据"长"在 UI 上。

- `{{ message }}` — 插值(显示文本)
- `:src="url"` — v-bind 缩写(动态属性)
- `@click="fn"` — v-on 缩写(事件监听)
- `v-model="text"` — 双向绑定(表单输入)

### 4. 列表渲染 — v-for + :key

**为什么**: 数组渲染列表必备。

```vue
<li v-for="item in items" :key="item.id">{{ item.title }}</li>
```

**`:key` 必须有**(用唯一 id,不要用 index),Vue 用 key 追踪元素,提升性能。

---

## 📁 本课最终目录结构

```
teacher_que_bank/                    ← C 方案单 repo 顶层
├── lesson-01/                       ← FastAPI Hello World
├── lesson-02/                       ← FastAPI 进阶
└── lesson-03/                       ← 本课新建(Vite 项目)
    ├── public/
    ├── src/
    │   ├── assets/
    │   ├── components/
    │   │   └── LessonList.vue       ← 新建(核心组件)
    │   ├── App.vue                  ← 改写(清空默认)
    │   └── main.js                  ← 入口(不改)
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── node_modules/                ← git ignore
```

---

## 🚀 老大要做的步骤(2 个文件)

### 步骤 1: 用 create-vue 建项目

```bash
cd ~/Desktop/dev/teacher_question_bank
npm create vue@latest lesson-03
```

交互式选项**全部选 No**(TS / JSX / Router / Pinia / Vitest / E2E / ESLint / Prettier / DevTools)。清爽不引依赖。

### 步骤 2: 装依赖 + 跑起来验证

```bash
cd lesson-03
npm install
npm run dev
```

浏览器打开 http://localhost:5173/ → 看到 Vue 默认欢迎页 = 成功。`Ctrl+C` 退出。

### 步骤 3: 改写 `src/App.vue`(清空默认)

```vue
<script setup>
import LessonList from './components/LessonList.vue'
</script>

<template>
  <header><h1>📚 教培题库 · 课程列表</h1></header>
  <main><LessonList /></main>
</template>

<style scoped>
header { text-align: center; padding: 24px; background: #f5f5f5; }
main { max-width: 720px; margin: 24px auto; padding: 0 16px; }
</style>
```

### 步骤 4: 新建 `src/components/LessonList.vue`

```vue
<script setup>
import { ref, computed } from 'vue'

const lessons = ref([
  { id: 1, title: '第 1 课：环境搭建 + Hello World', done: true },
  { id: 2, title: '第 2 课：FastAPI 入门', done: true },
  { id: 3, title: '第 3 课：Vue 3 入门', done: false },
  { id: 4, title: '第 4 课：前后端打通', done: false },
  { id: 5, title: '第 5 课：上传图片', done: false },
])

const completedCount = computed(
  () => lessons.value.filter(l => l.done).length
)
const totalCount = computed(() => lessons.value.length)

const newTitle = ref('')
function addLesson() {
  const title = newTitle.value.trim()
  if (!title) return
  const newId = Math.max(...lessons.value.map(l => l.id)) + 1
  lessons.value.push({ id: newId, title: `第 ${newId} 课：${title}`, done: false })
  newTitle.value = ''
}
function toggleDone(lesson) { lesson.done = !lesson.done }
function deleteLesson(id) {
  lessons.value = lessons.value.filter(l => l.id !== id)
}
</script>

<template>
  <div class="lesson-list">
    <h2>📖 学习进度（{{ completedCount }} / {{ totalCount }}）</h2>

    <div class="add-form">
      <input v-model="newTitle" placeholder="新课程标题..." @keyup.enter="addLesson" />
      <button @click="addLesson">+ 添加</button>
    </div>

    <ul>
      <li v-for="lesson in lessons" :key="lesson.id" :class="{ done: lesson.done }">
        <input type="checkbox" :checked="lesson.done" @change="toggleDone(lesson)" />
        <span class="title">{{ lesson.title }}</span>
        <button class="delete" @click="deleteLesson(lesson.id)">×</button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.add-form { display: flex; gap: 8px; margin-bottom: 16px; }
.add-form input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
.add-form button { padding: 8px 16px; background: #42b883; color: white; border: none; border-radius: 4px; cursor: pointer; }
ul { list-style: none; padding: 0; }
li { display: flex; align-items: center; gap: 12px; padding: 12px; border-bottom: 1px solid #eee; }
li.done .title { text-decoration: line-through; color: #999; }
.delete { margin-left: auto; background: #ff5555; color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; }
</style>
```

### 步骤 5: 跑起来

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-03
npm run dev
```

访问 http://localhost:5173/ → 看到课程列表 + 进度 + 添加 + 切换 + 删除 = 成功。

---

## 🎁 4 个动手做任务(预计 20-40 分钟)

### 任务 1: "全部完成 / 全部重置"按钮
```vue
<button @click="lessons.forEach(l => l.done = true)">✓ 全部完成</button>
<button @click="lessons.forEach(l => l.done = false)">↻ 全部重置</button>
```
放在进度条下面。

### 任务 2: 加筛选(全部 / 待完成 / 已完成)
```js
const filterMode = ref('all')
const filteredLessons = computed(() => {
  if (filterMode.value === 'pending') return lessons.value.filter(l => !l.done)
  if (filterMode.value === 'done') return lessons.value.filter(l => l.done)
  return lessons.value
})
```
把 `v-for="lesson in lessons"` 改成 `v-for="lesson in filteredLessons"`,加 3 个按钮切 filterMode。

### 任务 3: localStorage 持久化
```js
import { ref, computed, watch } from 'vue'

const saved = localStorage.getItem('lessons')
const lessons = ref(saved ? JSON.parse(saved) : [/* 初始数据 */])

watch(lessons, (newVal) => {
  localStorage.setItem('lessons', JSON.stringify(newVal))
}, { deep: true })
```
页面刷新数据不丢。

### 任务 4(可选): 加进度条
```vue
<div class="progress">
  <div class="bar" :style="{ width: (completedCount / totalCount * 100) + '%' }"></div>
</div>
```
```css
.progress { background: #eee; height: 8px; border-radius: 4px; overflow: hidden; }
.bar { background: #42b883; height: 100%; transition: width 0.3s; }
```
可视化进度。

---

## 📦 提交到 GitHub

```bash
cd ~/Desktop/dev/teacher_question_bank

# 顶层 .gitignore 加 node_modules/(Vite 自动生成的 .gitignore 只在 lesson-03/ 内)
# 检查: cat .gitignore | grep node_modules
# 没有就追加: echo "node_modules/" >> .gitignore

git add lesson-03/
git commit -m "feat(lesson-03): Vue 3 入门 + 课程列表组件"

git push origin main   # C 方案线性 main,不需 --force
```

**重要**: lesson-03 不需要 `--force`。lesson-02 已经把 main 摆正了,lesson-03 是普通的新 commit。

---

## ✅ 验收清单

- [ ] 项目按 create-vue 脚手架建好
- [ ] `npm install` + `npm run dev` 跑通
- [ ] 浏览器看到课程列表(5 条初始数据)
- [ ] checkbox 切换状态 → 进度数字变
- [ ] 输入框 + 添加按钮能加新课程
- [ ] × 按钮能删课程
- [ ] 至少做完任务 1-2
- [ ] 代码 push 到 GitHub(不需 force)

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| `npm create vue@latest` 卡住 | 检查镜像:`npm config get registry` 应是 npmmirror.com |
| `npm install` EACCES 报错 | 不要 `sudo npm install`,前面别用 sudo 启动 npm |
| 浏览器空白 | 看 Vite 终端有没有报错;默认端口 5173 |
| 修改 .vue 没反应 | Vite 自动 HMR,不行就 `Ctrl+C` 重启 |
| ref 改了页面没变 | template 自动 unwrap,script 里要用 `.value` |

---

## ⏭️ 完成后

我帮你 review + 开始 **Lesson 04: 前后端打通**(axios 调 FastAPI / CORS 解决 / 假数据换真数据)。

---

## 📚 速查表

```vue
<!-- 响应式数据 -->
import { ref, reactive, computed, watch } from 'vue'

const count = ref(0)                  // 基本类型
count.value = 1                       // script 里要 .value
count                                 // template 里不用 .value

const state = reactive({ name: 'x' }) // 对象
state.name = 'y'                      // 不用 .value

<!-- 模板语法 -->
{{ message }}              <!-- 插值(显示) -->
:src="url"                 <!-- v-bind 缩写(动态属性) -->
@click="fn"                <!-- v-on 缩写(事件) -->
v-model="text"             <!-- 双向绑定(表单) -->

<!-- 列表渲染 -->
<li v-for="item in items" :key="item.id">
  {{ item.title }}
</li>

<!-- 计算属性 -->
const completed = computed(() => lessons.value.filter(l => l.done).length)
{{ completed }}            <!-- template 自动 unwrap -->

<!-- 监听变化 -->
watch(lessons, (newVal) => {
  localStorage.setItem('lessons', JSON.stringify(newVal))
}, { deep: true })
```

---

## 🧠 这一课的"为什么"多说一句

按理 lesson-03 可以拆成 3-4 课(组件 / 响应式 / 模板 / 列表), 但老大风格是"读完赶紧上手", 所以**一次性给你看全**。每课重点记住:

- 看到 `<script setup>` + `ref(...)` → 知道是组件 + 响应式
- 看到 `{{ }}` / `v-bind` / `v-on` / `v-model` → 知道是模板语法
- 看到 `v-for` + `:key` → 知道是列表

**后面所有前端课都用这套结构**。你习惯了, 后面的速度会飞快。

晚安! 🌙