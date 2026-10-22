<script setup>
import { ref } from 'vue'
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
import OcrResult from './components/OcrResult.vue'

// === 任务 4:OcrResult 需要能换图,所以提到 App.vue 管理 ===
// 初始还是 lesson-06 主体写死的路径;上传成功后再由 UploadImage 回调覆盖
const currentImage = ref('/uploads/test-question.png')

function onUploaded(url) {
  currentImage.value = url
}
</script>

<template>
  <div class="app">
    <h1>📚 教培题库 · 课程列表</h1>
    <LessonList />
    <UploadImage @uploaded="onUploaded" />
    <OcrResult v-model:image-url="currentImage" />
  </div>
</template>