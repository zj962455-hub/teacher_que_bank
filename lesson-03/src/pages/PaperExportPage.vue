<script setup>
/**
 * PaperExportPage — ⑧ 试卷预览/导出
 *
 * 原型：A4 预览 + PDF/JPG 导出
 * 现在先做 PDF 导出（JPG 是下一轮的），并展示试卷内容预览。
 */
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NButton, NSpace, NSpin, NAlert, NDivider } from 'naive-ui'
import { getPaper, exportPaperPdf } from '../api/papers'
import { renderMathText } from '../utils/mathRenderer'

const route = useRoute()
const router = useRouter()

const paper = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const exporting = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await getPaper(route.params.id)
    paper.value = res.data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function doExport() {
  exporting.value = true
  errorMsg.value = ''
  try {
    const filename = await exportPaperPdf(paper.value.id, paper.value.title)
    // 导出成功给个提示（文件已下载）
    errorMsg.value = ''
    console.log('已导出:', filename)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `导出失败：${e.message}`
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div>
    <div class="page-head">
      <NButton size="small" quaternary @click="router.push({ name: 'papers' })">
        ← 我的试卷
      </NButton>
      <NSpace v-if="paper">
        <NButton size="small" type="primary" :loading="exporting" @click="doExport">
          导出 PDF
        </NButton>
      </NSpace>
    </div>

    <NAlert v-if="errorMsg" type="error" :bordered="false">{{ errorMsg }}</NAlert>

    <NSpin :show="loading">
      <NCard v-if="paper" style="margin-top: 12px" :title="paper.title">
        <div v-if="paper.subtitle" class="subtitle">{{ paper.subtitle }}</div>

        <NDivider />

        <div v-for="q in paper.questions" :key="q.id" class="question">
          <div class="q-head">
            <span class="q-label">{{ q.label }}</span>
            <span class="q-content" v-html="renderMathText(q.question.content_markdown || q.question.content_plain)" />
            <span v-if="q.score" class="q-score">{{ q.score }} 分</span>
          </div>
        </div>

        <NAlert v-if="!paper.questions?.length" type="info" :bordered="false">
          这张试卷还没有题目。
        </NAlert>
      </NCard>
    </NSpin>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.subtitle {
  color: #666;
  font-size: 13px;
}

.question {
  margin-bottom: 14px;
}

.q-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 14px;
  line-height: 1.9;
}

.q-label {
  font-weight: 600;
  flex-shrink: 0;
}

.q-content {
  flex: 1;
}

.q-score {
  color: #999;
  font-size: 12px;
  flex-shrink: 0;
}
</style>
