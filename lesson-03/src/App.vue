<script setup>
import LessonList from './components/LessonList.vue'
import UploadImage from './components/UploadImage.vue'
</script>

<template>
  <div class="app">
    <h1>📚 教培题库 · 课程列表</h1>
    <LessonList />
    <UploadImage />
  </div>
</template>

<style>
.app { max-width: 800px; margin: 0 auto; padding: 24px; font-family: system-ui; }
</style>