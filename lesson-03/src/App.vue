<script setup>
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
import OcrResult from './components/OcrResult.vue'   // ← 新增
</script>

<template>
  <div class="app">
    <h1>📚 教培题库 · 课程列表</h1>
    <LessonList />
    <UploadImage />
    <OcrResult image-url="/uploads/sample.jpg" />   <!-- ← 临时写死,lesson-XX 接 UploadImage 上传成功后回调 -->
  </div>
</template>