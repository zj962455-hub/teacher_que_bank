# Lesson 04 精简注释版 · 前后端打通

> 在 lesson-02 FastAPI 后端 + lesson-03 Vue 3 前端基础上,**学 4 件大事**:
> 1. **axios** — Vue 端 HTTP 客户端
> 2. **CORS** — FastAPI 端跨域允许
> 3. **async/await** — 异步请求(lesson-02 标的 async 反模式这次用上真异步了)
> 4. **onMounted** — Vue 组件挂载时拉数据
>
> 这一课是分水岭——前面 lesson-01/02/03 都各管各的,这一课把前后端接上,以后所有课都在"已打通"的基础上加功能。

---

## 🧠 4 个核心概念(读 1 分钟)

### 1. axios — HTTP 客户端

**为什么**: Vue 自己有 `fetch()`,但 axios DX 更好(自动解析 JSON、拦截器、错误处理统一)。

**类比**: axios ≈ Python 的 `requests` 库——发 HTTP 请求拿响应,一行代码。

```js
import axios from 'axios'
const res = await axios.get('/api/courses')
console.log(res.data)  // 注意:axios 把 JSON 自动解析到 res.data,不是 res.body
```

### 2. CORS — 跨域资源共享

**为什么**: 浏览器**同源策略**会阻止 `localhost:5173` (Vite) 访问 `localhost:8000` (FastAPI)——不同端口 = 不同源 = 浏览器拒绝。

**类比**: 公司门禁——A 楼的人想去 B 楼,B 楼门禁系统得"白名单"放行。FastAPI 端要加 CORS 中间件告诉浏览器:"5173 是友军,放行"。

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. async/await — 异步请求(lesson-02 反模式这次用上了)

**为什么 lesson-02 我让你改 `async def` 改回 `def`**——因为当时函数体没有 IO,async 没意义。这次**真有 IO 了**(网络请求),async/await 派上用场。

```js
async function loadCourses() {
  const res = await axios.get('/api/courses')  // 等网络回来
  lessons.value = res.data                     // 拿到数据后赋值
}
```

### 4. onMounted — Vue 生命周期钩子

**为什么**: "页面打开时调一次 API"是固定动作,Vue 给这个时点起了个名字 `onMounted`。

```js
import { onMounted } from 'vue'

onMounted(async () => {
  const res = await axios.get('/api/courses')
  lessons.value = res.data
})
```

**类比 FastAPI**: 想象 `@app.on_event("startup")` —— 服务起来时跑一次。Vue 的 `onMounted` 就是组件"挂载到 DOM"时跑一次。

---

## 📁 本课最终改动(C 方案:不新建 lesson-04/ 目录)

```
teacher_que_bank/
├── lesson-02/                              ← 后端改动
│   └── app/
│       ├── main.py                          ← 加 CORSMiddleware + include_router(courses)
│       └── routers/
│           ├── lessons.py                   ← 不动(lesson-02 已 push)
│           └── courses.py                   ← 新增(本课)
└── lesson-03/                              ← 前端改动
    ├── package.json                         ← 加 axios 依赖
    └── src/
        └── components/
            └── LessonList.vue               ← 改:onMounted + axios 调真实 API
```

**为什么 lesson-04 不建目录**: lesson-04 是 lesson-02/03 的**增量**,不是独立项目。C 方案下 lesson-XX 应该线性累加,不是平行多份。

---

## 🚀 老大要做的步骤(4 个文件)

### 步骤 1: 后端新增 `lesson-02/app/routers/courses.py`

```python
"""用户学习进度路由组 - lesson-04 重点:返回结构化数据给 Vue 用"""
from fastapi import APIRouter

router = APIRouter(
    prefix="/courses",
    tags=["课程进度"],
)

# 模拟"用户学习进度"数据(后期换成数据库)
fake_courses = [
    {"id": 1, "title": "第 1 课:环境搭建 + Hello World", "done": True},
    {"id": 2, "title": "第 2 课:FastAPI 入门", "done": True},
    {"id": 3, "title": "第 3 课:Vue 3 入门", "done": False},
    {"id": 4, "title": "第 4 课:前后端打通", "done": False},
    {"id": 5, "title": "第 5 课:上传图片", "done": False},
]


@router.get("/")
def list_courses():
    """返回课程列表(含完成状态)"""
    return fake_courses
```

**注意**:
- 返回的是**对象数组**(不是 lesson-02 的字符串数组)——Vue 要结构化数据
- lesson-02 的 `/api/lessons/` 仍然返回字符串数组(课程元信息),不动

### 步骤 2: 后端改 `lesson-02/app/main.py` —— 加 CORS + 注册 courses

```python
"""FastAPI 应用入口 - 负责组装,不写业务"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import lessons, courses

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.1.0",
)

# === lesson-04 新增:CORS 中间件(允许 Vite 5173 访问) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由组
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.1.0",
    }
```

**核心点**:
- `CORSMiddleware` 是 FastAPI 内置中间件,导入即用
- `allow_origins=["http://localhost:5173"]` 只允许 Vite 默认端口
- lesson-04 阶段**开发态**这样写够了;**生产态**要把域名换成 `https://lanhu-lab.top` 之类

### 步骤 3: 前端装 axios

```bash
cd ~/Desktop/dev/teacher_question_bank/lesson-03
npm install axios
```

**会改**:
- `package.json` 加 `"axios": "^1.x.x"` 到 dependencies
- `package-lock.json` 自动更新
- `node_modules/axios/` 自动装好

### 步骤 4: 前端改 `lesson-03/src/components/LessonList.vue`

**完整改写**(lesson-03 假数据 → lesson-04 真实 API):

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

// === 响应式数据 ===
const lessons = ref([])              // 初始空数组,从 API 加载
const loading = ref(false)           // 加载状态
const error = ref(null)              // 错误信息

// === 计算属性 ===
const completedCount = computed(
  () => lessons.value.filter(l => l.done).length
)
const totalCount = computed(() => lessons.value.length)

const newTitle = ref('')
const filterMode = ref('all')

const filteredLessons = computed(() => {
  if (filterMode.value === 'pending') return lessons.value.filter(l => !l.done)
  if (filterMode.value === 'done')    return lessons.value.filter(l => l.done)
  return lessons.value
})

const progressPercent = computed(() =>
  totalCount.value ? Math.round(completedCount.value / totalCount.value * 100) : 0
)

// === 加载课程(从 FastAPI 真实 API) ===
async function loadCourses() {
  loading.value = true
  error.value = null
  try {
    const res = await axios.get('http://localhost:8000/api/courses/')
    lessons.value = res.data
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

// === 组件挂载时加载一次 ===
onMounted(loadCourses)

// === 操作 ===
async function addLesson() {
  const title = newTitle.value.trim()
  if (!title) return
  // 本地立刻加(乐观更新)+ 调 API 同步后端
  const newId = lessons.value.length
    ? Math.max(...lessons.value.map(l => l.id)) + 1
    : 1
  const newCourse = { id: newId, title: `第 ${newId} 课:${title}`, done: false }
  lessons.value.push(newCourse)
  newTitle.value = ''
  // TODO lesson-08 接数据库后再调 POST API,这里先纯本地
}

function toggleDone(lesson) {
  lesson.done = !lesson.done
  // TODO lesson-08 调 PATCH API
}

async function deleteLesson(id) {
  lessons.value = lessons.value.filter(l => l.id !== id)
  // TODO lesson-08 调 DELETE API
}
</script>

<template>
  <div class="lesson-list">
    <h2>📖 学习进度({{ completedCount }} / {{ totalCount }})</h2>

    <div class="progress">
      <div class="bar" :style="{ width: progressPercent + '%' }"></div>
    </div>

    <!-- 加载 / 错误 / 空 三种状态 -->
    <div v-if="loading" class="status">⏳ 加载中...</div>
    <div v-else-if="error" class="status error">❌ {{ error }}</div>
    <div v-else-if="!lessons.length" class="status">📭 还没有课程</div>

    <template v-else>
      <div class="add-form">
        <input v-model="newTitle" placeholder="新课程标题..." @keyup.enter="addLesson" />
        <button @click="addLesson">+ 添加</button>
      </div>

      <div class="filters">
        <button :class="{ active: filterMode === 'all' }" @click="filterMode = 'all'">全部</button>
        <button :class="{ active: filterMode === 'pending' }" @click="filterMode = 'pending'">待完成</button>
        <button :class="{ active: filterMode === 'done' }" @click="filterMode = 'done'">已完成</button>
      </div>

      <ul>
        <li v-for="lesson in filteredLessons" :key="lesson.id" :class="{ done: lesson.done }">
          <input type="checkbox" :checked="lesson.done" @change="toggleDone(lesson)" />
          <span class="title">{{ lesson.title }}</span>
          <button class="delete" @click="deleteLesson(lesson.id)">×</button>
        </li>
      </ul>

      <button @click="lessons.forEach(l => l.done = true)">✓ 全部完成</button>
      <button @click="lessons.forEach(l => l.done = false)">↻ 全部重置</button>
    </template>
  </div>
</template>

<style scoped>
/* ... 跟 lesson-03 一样 ... */
.status { padding: 24px; text-align: center; color: #666; }
.status.error { color: #c00; }
/* 其他样式从 lesson-03 复制 */
</style>
```

**核心点**:
- `onMounted(loadCourses)` —— 组件挂载时自动调 API
- `loading` / `error` 三态显示 —— v-if / v-else-if
- `try/catch/finally` —— 网络错误友好提示
- **暂时删掉 localStorage**(lesson-03 的 watch)—— 真实数据从后端来,localStorage 会导致前后端不一致

### 步骤 5: 同时跑 FastAPI + Vite

```bash
# 终端 1: FastAPI 后端
cd ~/Desktop/dev/teacher_question_bank/lesson-02
source ../lesson-01/venv/bin/activate
uvicorn app.main:app --reload

# 终端 2: Vue 前端
cd ~/Desktop/dev/teacher_question_bank/lesson-03
npm run dev
```

浏览器打开 http://localhost:5173/ → 应该看到 5 条课程从 FastAPI 加载。

**测试 CORS 是否生效**:
- 在 DevTools Console 跑 `fetch('http://localhost:8000/api/courses/').then(r => r.json()).then(console.log)`
- 应该看到 5 条课程,**没有 CORS 错误**

---

## 🎁 4 个动手做任务(预计 30-60 分钟)

### 任务 1: 加一个"刷新"按钮
```vue
<button @click="loadCourses">🔄 刷新</button>
```
手动重新拉一次。

### 任务 2: 加请求超时处理
```js
const res = await axios.get('http://localhost:8000/api/courses/', {
  timeout: 3000,  // 3 秒超时
})
```

### 任务 3: 调 FastAPI `/api/lessons/{id}` 详情接口
- 在 FastAPI `routers/courses.py` 加 `@router.get("/{course_id}")`
- Vue 端点 li 时调详情接口(可以用 modal 显示完整信息)
- 触发 404 / 422 测错误处理

### 任务 4(可选): 自动轮询(每 5 秒刷新一次)
```js
import { onMounted, onUnmounted } from 'vue'

let timer = null
onMounted(() => {
  loadCourses()
  timer = setInterval(loadCourses, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
```
**注意**: `onUnmounted` 清理定时器——避免组件卸载后定时器还在跑(内存泄漏)。

---

## 📦 提交到 GitHub

lesson-04 改动跨 lesson-02/03(后端改 lesson-02,前端改 lesson-03),但**都包在一个 commit 里**:

```bash
cd ~/Desktop/dev/teacher_question_bank

# 后端改动
git add lesson-02/app/routers/courses.py \
        lesson-02/app/main.py

# 前端改动(package-lock.json 自动更新)
git add lesson-03/package.json \
        lesson-03/package-lock.json \
        lesson-03/src/components/LessonList.vue

git commit -m "feat(lesson-04): 前后端打通 + axios + CORS"

git push origin main   # C 方案线性 main,不需 force
```

---

## ✅ 验收清单

- [ ] `routers/courses.py` 创建,返回结构化数据
- [ ] `main.py` 加了 CORS 中间件
- [ ] FastAPI 启动后 `curl http://localhost:8000/api/courses/` 返回 5 条
- [ ] 前端装好 axios
- [ ] LessonList.vue 改用 onMounted + axios
- [ ] 浏览器打开 Vite,看到 5 条课程(从 FastAPI 加载)
- [ ] DevTools Console 没有 CORS 错误
- [ ] 至少做完任务 1-2
- [ ] 代码 push 到 GitHub(不需 force)

---

## 🆘 卡住怎么办

| 问题 | 解决 |
|---|---|
| CORS 报错 `Access-Control-Allow-Origin` | 检查 FastAPI `CORSMiddleware` 是否加,`allow_origins` 是否含 `http://localhost:5173` |
| 浏览器报 `Network Error` | FastAPI 没启动,或端口错(8000 vs 5173) |
| `axios is not defined` | 没装 axios:`npm install axios`,或忘了 `import axios from 'axios'` |
| `res.data` 是字符串不是数组 | axios 拦截器问题;直接打印 `res` 看结构 |
| onMounted 里改 ref 没反应 | 检查是不是在 setup 外调用 ref;ref 在 setup 里是 top-level 才能用 |
| 同时跑两个服务忘关 | `Ctrl+C` 关 Vite/FastAPI 各自终端 |

---

## ⏭️ 完成后

我帮你 review + 开始 **Lesson 05: 上传图片**(FormData / File / 前后端上传 + 预览)。

---

## 📚 速查表

```js
// axios
import axios from 'axios'
const res = await axios.get('/api/xxx')           // GET
const res = await axios.post('/api/xxx', data)     // POST
res.data                                            // 注意是 .data 不是 .body

// onMounted
import { onMounted, onUnmounted } from 'vue'
onMounted(() => { /* 组件挂载时跑一次 */ })
onUnmounted(() => { /* 组件卸载时清理 */ })

// async/await(真异步)
async function load() {
  try {
    const res = await axios.get('/api/xxx')
    lessons.value = res.data
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// v-if 三态显示
<div v-if="loading">加载中...</div>
<div v-else-if="error">错误: {{ error }}</div>
<div v-else-if="!data.length">空数据</div>
<div v-else>... 显示数据 ...</div>
```

```python
# FastAPI CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🧠 这一课的"为什么"多说一句

前面 lesson-01/02/03 都"各管各的"——FastAPI 自己跑,Vue 自己跑。**lesson-04 是分水岭**,前后端接上后,后面所有课都在"已打通"的基础上加功能:

- lesson-05 上传图片 = Vue 发 POST + FastAPI 接收 + 数据库存
- lesson-06 调 OCR = Vue 上传后等 FastAPI 返回识别结果
- lesson-08 存数据库 = 把 fake_courses 换成 SQLModel 真数据库

**跨 lesson 修改是 C 方案的"超能力"**:lesson-04 改 lesson-02/lesson-03 是因为现实项目就是改来改去,不是 lesson 之间隔离。你习惯这个,后面不会纠结"该改哪个文件"。

晚安! 🌙(老大应该是白天看 Vue 代码 + 看这文档,那就日安 ☀️)