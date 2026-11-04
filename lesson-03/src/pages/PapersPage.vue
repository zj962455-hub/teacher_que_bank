<script setup>
/**
 * PapersPage — ⑦ 组卷页
 *
 * 原型：三栏（题目筛选 + 列表 + 试卷区，拖拽排序）
 * 现在复用 PaperEditor（已在用），先把页面结构立起来，
 * 三栏布局和拖拽排序是下一轮补的。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import PaperEditor from '../components/PaperEditor.vue'

const router = useRouter()
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">📄 组卷</h2>
      <NButton size="small" quaternary @click="router.push({ name: 'papers' })">
        我的试卷
      </NButton>
    </div>

    <PaperEditor />
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  font-size: 18px;
}
</style>
