<script setup>
import { ref, onMounted } from 'vue'
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
import OcrResult from './components/OcrResult.vue'
import QuestionBank from './components/QuestionBank.vue'   // ← lesson-08 题库列表
import QuestionEditor from './components/QuestionEditor.vue'  // ← lesson-09 题目编辑
import PaperEditor from './components/PaperEditor.vue'      // ← lesson-09 组卷
import SiteFooter from './components/SiteFooter.vue'          // ← 备案号页脚
import LoginPanel from './components/LoginPanel.vue'          // ← lesson-11 登录
import { getToken, getCachedUser, fetchMe, setUnauthorizedHandler } from './api/auth'

// === lesson-11:登录门禁 ===
// 后端所有业务接口都要 Authorization 头，没 token 直接 401。
// 所以前端先判断登录态：没登录就只显示登录面板，不渲染业务组件
// （渲染了也全是 401 白屏）。
const loggedIn = ref(!!getToken())
const currentUser = ref(getCachedUser())

// 启动时校验 token 还有效（本地有 token 但服务端已过期的情况）
onMounted(async () => {
  if (!getToken()) return
  try {
    currentUser.value = await fetchMe()
    loggedIn.value = true
  } catch {
    // token 失效 → 拦截器已经清了 + 触发 onUnauthorized
    loggedIn.value = false
  }
})

// 后端返 401 时（token 过期 / 被踢下线）→ 回到登录态
setUnauthorizedHandler(() => {
  loggedIn.value = false
  currentUser.value = null
})

function onLoggedIn(user) {
  currentUser.value = user
  loggedIn.value = true
}

// === 任务 4:OcrResult 需要能换图,所以提到 App.vue 管理 ===
// 初始还是 lesson-06 主体写死的路径;上传成功后再由 UploadImage 回调覆盖
// ⚠️ 初始为空 —— 静态挂载时代写死的 /uploads/test-question.png
//    在服务器上根本不存在，且图片接口现在要鉴权
const currentImage = ref('')

function onUploaded(url) {
  currentImage.value = url
}

// OCR 卡片入库成功 → 刷新题库列表
const bankRef = ref(null)

function onQuestionSaved() {
  bankRef.value?.refresh()
}

// lesson-09:打开题目编辑器(编辑题库里已存的题)
const editingQuestion = ref(null)

function openQuestionEditor(row) {
  editingQuestion.value = row
}
</script>

<template>
  <div class="app">
    <!-- 未登录：只显示登录面板（业务组件不渲染，否则全是 401） -->
    <template v-if="!loggedIn">
      <LoginPanel @logged-in="onLoggedIn" />
      <SiteFooter />
    </template>

    <!-- 已登录：业务界面 -->
    <template v-else>
      <h1>📚 教培题库 · 课程列表</h1>
      <LessonList />
      <UploadImage @uploaded="onUploaded" />
      <OcrResult v-model:image-url="currentImage" @question-saved="onQuestionSaved" />
      <QuestionBank ref="bankRef" @edit="openQuestionEditor" />
      <PaperEditor />

      <!-- lesson-09:编辑题库里已存的题目 -->
      <QuestionEditor
        v-if="editingQuestion"
        mode="edit"
        :question-id="editingQuestion.id"
        :plain-text="editingQuestion.content_plain"
        :with-formulas="editingQuestion.content_markdown"
        :blocks="editingQuestion.blocks"
        @close="editingQuestion = null"
        @saved="onQuestionSaved"
      />

      <!-- 页脚 · ICP 备案号(公安联网备案要求公示) -->
      <SiteFooter />
    </template>
  </div>
</template>