<script setup>
/**
 * CategoriesPage — ⑥ 分类管理
 *
 * 原型：章节树维护 + 拖拽排序 + 题目统计
 * 现在先用 LessonList（课程 + 章节列表）撑住页面，
 * 拖拽排序和统计是下一轮补的。
 */
import { ref } from 'vue'
import { NButton } from 'naive-ui'
import { useRouter } from 'vue-router'
import LessonList from '../components/LessonList.vue'

const router = useRouter()
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">🗂 分类管理</h2>
      <NButton size="small" quaternary @click="router.push({ name: 'questions' })">
        去题库
      </NButton>
    </div>

    <p class="page-desc">
      维护课程和章节结构。章节是题目的归属维度，改动会影响筛选。
    </p>

    <LessonList />
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: 18px;
}

.page-desc {
  color: #666;
  font-size: 13px;
  margin: 0 0 16px;
}
</style>
