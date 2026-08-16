<script setup>
import { ref, computed, watch } from 'vue'

const STORAGE_KEY = 'lessons'
const saved = localStorage.getItem(STORAGE_KEY)
const lessons = ref(saved ? JSON.parse(saved) : [
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

const filterMode = ref('all')  // 'all' | 'pending' | 'done'

const filteredLessons = computed(() => {
  if (filterMode.value === 'pending') return lessons.value.filter(l => !l.done)
  if (filterMode.value === 'done')    return lessons.value.filter(l => l.done)
  return lessons.value
})

const progressPercent = computed(() =>
  totalCount.value ? Math.round(completedCount.value / totalCount.value * 100) : 0
)

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

watch(lessons, (newVal) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(newVal))
}, { deep: true })
</script>

<template>
  <div class="lesson-list">
    <h2>📖 学习进度（{{ completedCount }} / {{ totalCount }}）</h2>

    <div class="progress">
      <div class="bar" :style="{ width: progressPercent + '%' }"></div>
    </div>
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
.filters button.active { background: #42b883; color: white; }
.progress { background: #eee; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 16px; }
.bar { background: #42b883; height: 100%; transition: width 0.3s; }
</style>