<script setup>
import { ref } from 'vue'
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
import OcrResult from './components/OcrResult.vue'
import QuestionBank from './components/QuestionBank.vue'   // ← lesson-08 题库列表
import QuestionEditor from './components/QuestionEditor.vue'  // ← lesson-09 题目编辑
import PaperEditor from './components/PaperEditor.vue'      // ← lesson-09 组卷

// === 任务 4:OcrResult 需要能换图,所以提到 App.vue 管理 ===
// 初始还是 lesson-06 主体写死的路径;上传成功后再由 UploadImage 回调覆盖
const currentImage = ref('/uploads/test-question.png')

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
  </div>
</template>