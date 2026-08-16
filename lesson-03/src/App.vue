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