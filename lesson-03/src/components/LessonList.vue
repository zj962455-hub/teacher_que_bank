<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

// === 响应式数据 ===
const lessons = ref([])              // 初始空数组,从 API 加载
const loading = ref(false)           // 加载状态
const error = ref(null)              // 错误信息
// 详情 modal 状态
const showModal = ref(false)
const selectedCourse = ref(null)
const modalError = ref(null)
const modalLoading = ref(false)

//5s轮询一次
// let timer = null
// onMounted(() => {
//   loadCourses()
//   timer = setInterval(loadCourses, 5000)
// })
// onUnmounted(() => {
//   if (timer) clearInterval(timer)
// })


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
    const res = await axios.get('http://localhost:8000/api/courses/', {
  timeout: 3000,  // 3 秒超时
})
    lessons.value = res.data
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

// === 组件挂载时加载一次 ===
onMounted(loadCourses)
async function openCourseDetail(courseId) {
  showModal.value = true
  selectedCourse.value = null
  modalError.value = null
  modalLoading.value = true
  try {
    const res = await axios.get(`http://localhost:8000/api/courses/${courseId}`, { timeout: 3000 })
    selectedCourse.value = res.data
  } catch (e) {
    if (e.response?.status === 404) {
      modalError.value = `课程 ${courseId} 不存在`
    } else {
      modalError.value = `加载失败: ${e.message}`
    }
  } finally {
    modalLoading.value = false
  }
}

function closeModal() {
  showModal.value = false
  selectedCourse.value = null
  modalError.value = null
}

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
          <span class="title clickable" @click="openCourseDetail(lesson.id)">{{ lesson.title }}</span>
          <button class="delete" @click="deleteLesson(lesson.id)">×</button>
        </li>
      </ul>

      <button @click="lessons.forEach(l => l.done = true)">✓ 全部完成</button>
      <button @click="lessons.forEach(l => l.done = false)">↻ 全部重置</button>
      <button @click="loadCourses">🔄 刷新</button>
    </template>
  </div>
  <div v-if="showModal" class="modal-overlay" @click="closeModal">
  <div class="modal" @click.stop>
    <div v-if="modalLoading">⏳ 加载中...</div>
    <div v-else-if="modalError" class="error">❌ {{ modalError }}</div>
    <div v-else-if="selectedCourse">
      <h3>📖 课程详情</h3>
      <p><strong>ID:</strong> {{ selectedCourse.id }}</p>
      <p><strong>标题:</strong> {{ selectedCourse.title }}</p>
      <p><strong>状态:</strong> {{ selectedCourse.done ? '✅ 已完成' : '⏳ 待完成' }}</p>
      <button @click="closeModal">关闭</button>
    </div>
  </div>
</div>
</template>

<style scoped>
/* ... 跟 lesson-03 一样 ... */
.status { padding: 24px; text-align: center; color: #666; }
.status.error { color: #c00; }
.add-form { display: flex; gap: 8px; margin-bottom: 16px; }
.add-form input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
.add-form button { padding: 8px 16px; background: #42b883; color: white; border: none; border-radius: 4px; cursor: pointer; }
ul { list-style: none; padding: 0; }
li { display: flex; align-items: center; gap: 12px; padding: 12px; border-bottom: 1px solid #eee; }
li.done .title { text-decoration: line-through; color: #999; }
.delete { margin-left: auto; background: #ff5555; color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; }
.filters button.active { background: #42b883; color: white; }
.progress { background: #eee; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 16px; }
.bar { background: #42b883; height: 100%; transition: width 0.3s; }
.clickable { cursor: pointer; user-select: none; }
.clickable:hover { text-decoration: underline; }
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.modal { background: white; padding: 24px; border-radius: 8px; min-width: 320px; max-width: 80%; }
.modal .error { color: #c00; margin: 16px 0; }
</style>