<script setup>
/**
 * QuestionDetailPage — ⑤ 题目详情
 *
 * 原型：单题只读 + 编辑/加入试卷/分享/删除
 * 分享已砍（第一版不做），这里做只读展示 + 编辑 + 删除。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NSpin, NButton, NSpace, NTag, NDivider, NAlert } from 'naive-ui'
import { getQuestion, deleteQuestion } from '../api/questions'
import { dialog } from '../composables/discreteApi'
import { renderMathText } from '../utils/mathRenderer'
import QuestionEditor from '../components/QuestionEditor.vue'

const route = useRoute()
const router = useRouter()

const question = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const editing = ref(false)

const questionId = computed(() => route.params.id)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await getQuestion(questionId.value)
    question.value = res.data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)

function onSaved() {
  editing.value = false
  load()
}

function doDelete() {
  dialog.warning({
    title: '删除这道题？',
    content: '删了就找不回来了。',
    positiveText: '确认删除',
    negativeText: '再想想',
    onPositiveClick: async () => {
      try {
        await deleteQuestion(questionId.value)
        router.replace({ name: 'questions' })
      } catch (e) {
        errorMsg.value = e.response?.data?.detail || '删除失败'
      }
    },
  })
}
</script>

<template>
  <div>
    <div class="page-head">
      <NButton size="small" quaternary @click="router.push({ name: 'questions' })">
        ← 返回题库
      </NButton>
      <NSpace v-if="question">
        <NButton size="small" @click="editing = true">编辑</NButton>
        <NButton size="small" type="error" @click="doDelete">删除</NButton>
      </NSpace>
    </div>

    <NAlert v-if="errorMsg" type="error" :bordered="false">{{ errorMsg }}</NAlert>

    <NSpin :show="loading">
      <NCard v-if="question" style="margin-top: 12px">
        <div class="tags">
          <NTag size="small" :bordered="false">{{ question.subject }}</NTag>
          <NTag size="small" :bordered="false">{{ question.question_type }}</NTag>
          <NTag size="small" :bordered="false">{{ question.grade }}</NTag>
          <NTag size="small" :bordered="false">{{ question.difficulty }}</NTag>
        </div>

        <NDivider />

        <!-- 题干(公式用 KaTeX 渲染) -->
        <div class="content" v-html="renderMathText(question.content_markdown || question.content_plain)" />

        <NDivider />

        <div class="meta">
          创建于 {{ new Date(question.created_at).toLocaleString('zh-CN') }}
        </div>
      </NCard>
    </NSpin>

    <!-- 编辑 -->
    <QuestionEditor
      v-if="editing && question"
      mode="edit"
      :question-id="question.id"
      :plain-text="question.content_plain"
      :with-formulas="question.content_markdown"
      :blocks="question.blocks"
      @close="editing = false"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.content {
  font-size: 15px;
  line-height: 1.9;
}

.meta {
  font-size: 12px;
  color: #999;
}
</style>
