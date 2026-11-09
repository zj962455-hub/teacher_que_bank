<script setup>
/**
 * SharedPaperPage — 公开分享页（课 24）
 *
 * 这是**唯一不需要登录**的业务页
 * ------------------------------
 * 老师把分享链接发到微信群 / 学生家长群里，对方点开就要能直接看到卷子。
 * 要求对方先注册账号，这功能就没意义了。
 *
 * 页面本身不碰任何账号信息
 * ----------------------
 * 后端公开接口只返回卷子的题目内容，不含 owner id / 用户名 / 邮箱 ——
 * 前端也**不要**去调 /auth/me（那会带上本机 token，触发 401 拦截器清登录态）。
 *
 * 能做什么
 * --------
 * - 看卷子（题号 + 题干 + 分值）
 * - 下 PDF / 下 JPG（每页一张，ZIP）
 *
 * 链接失效时（过期 / 被吊销）→ 后端返 404 → 这里显示提示 + 返回题库首页的链接
 */
import { ref, onMounted } from 'vue'
import { NCard, NButton, NSpace, NSpin, NAlert, NDivider } from 'naive-ui'
import { getSharedPaper, downloadSharedPdf, downloadSharedJpg } from '../api/shares'
import { renderMathText } from '../utils/mathRenderer'
import { stripFigurePlaceholder } from '../utils/figurePlaceholder'   // ← lesson-38: 展示去掉【题图】占位
import { useRoute } from 'vue-router'

const route = useRoute()

const paper = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const exporting = ref(false)
const exportingJpg = ref(false)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await getSharedPaper(route.params.token)
    paper.value = res.data
    // 分享页标题带卷名 —— 老师把链接发到班级群，
    // 对方浏览器标签页 / 微信卡片标题能看出是哪张卷
    const name = res.data?.title
    document.title = name ? `${name} · 蓝狐题库` : '试卷分享 · 蓝狐题库'
  } catch (e) {
    document.title = '试卷分享 · 蓝狐题库'
    errorMsg.value =
      e.response?.status === 404
        ? '链接不存在、已过期或已被老师取消。'
        : e.response?.data?.detail || `加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function doExportPdf() {
  exporting.value = true
  errorMsg.value = ''
  try {
    await downloadSharedPdf(route.params.token)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `下载失败：${e.message}`
  } finally {
    exporting.value = false
  }
}

async function doExportJpg() {
  exportingJpg.value = true
  errorMsg.value = ''
  try {
    await downloadSharedJpg(route.params.token)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `下载失败：${e.message}`
  } finally {
    exportingJpg.value = false
  }
}
</script>

<template>
  <div class="shared-page">
    <NAlert v-if="errorMsg" type="error" :bordered="false">{{ errorMsg }}</NAlert>

    <NSpin :show="loading">
      <NCard v-if="paper" style="margin-top: 12px" :title="paper.title">
        <div v-if="paper.subtitle" class="subtitle">{{ paper.subtitle }}</div>

        <NSpace style="margin-top: 12px">
          <NButton type="primary" :loading="exporting" @click="doExportPdf">
            下载 PDF
          </NButton>
          <NButton :loading="exportingJpg" @click="doExportJpg">
            下载 JPG
          </NButton>
        </NSpace>

        <NDivider />

        <div v-for="(q, i) in paper.questions" :key="i" class="question">
          <div class="q-head">
            <span class="q-label">{{ q.label }}</span>
            <span class="q-content" v-html="renderMathText(stripFigurePlaceholder(q.content_markdown || q.content_plain))" />
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
/* 公开页比内页窄一点 —— 打印稿的样子，居中好读 */
.shared-page {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--tqb-space-4) var(--tqb-space-4) var(--tqb-space-8);
}

.subtitle {
  color: var(--tqb-text-secondary);
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
  color: var(--tqb-text-tertiary);
  font-size: 12px;
  flex-shrink: 0;
}
</style>
