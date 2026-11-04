<script setup>
/**
 * QuestionsPage — ③ 题目列表
 *
 * 原型：章节树筛选 + 关键词搜索 + 批量操作
 * 现在先把 QuestionBank（表格 + 筛选）搬过来独立成页，
 * 章节树筛选和批量操作是下一轮补的。
 */
import { ref } from 'vue'
import { NButton } from 'naive-ui'
import { useRouter } from 'vue-router'
import QuestionBank from '../components/QuestionBank.vue'
import QuestionEditor from '../components/QuestionEditor.vue'

const router = useRouter()
const bankRef = ref(null)
const editingQuestion = ref(null)

function openQuestionEditor(row) {
  editingQuestion.value = row
}

function onQuestionSaved() {
  bankRef.value?.refresh()
}
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">📚 题目列表</h2>
      <NButton type="primary" size="small" @click="router.push({ name: 'capture' })">
        + 录题
      </NButton>
    </div>

    <QuestionBank ref="bankRef" @edit="openQuestionEditor" />

    <!-- 编辑题库里已存的题目 -->
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
