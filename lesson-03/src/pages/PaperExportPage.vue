<script setup>
/**
 * PaperExportPage — ⑧ 试卷预览/导出 + 分享链接
 *
 * 原型：A4 预览 + PDF/JPG 导出 + 「🔗 生成分享链接（Web 端下载）」
 * 导出：PDF（打印稿）+ JPG（每页一张，打包 ZIP，发群用）。
 * 分享：带过期时间的公开链接（课 24），对方不用账号就能在浏览器看卷子、下文件。
 */
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NButton, NSpace, NSpin, NAlert, NDivider, NSelect, NInput, NTag } from 'naive-ui'
import { getPaper, exportPaperPdf, exportPaperJpg } from '../api/papers'
import { createShare, listShares, revokeShare, buildShareUrl } from '../api/shares'
import { parseError } from '../utils/errors'   // ← 课 32:统一错误解析
import { renderMathText } from '../utils/mathRenderer'

const route = useRoute()
const router = useRouter()

const paper = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const exporting = ref(false)
const exportingJpg = ref(false)

// === 分享链接（课 24）===
const shares = ref([])
const sharesLoading = ref(false)
const creating = ref(false)
const expireHours = ref(168)
const lastCreated = ref('')

const EXPIRE_OPTIONS = [
  { label: '1 小时', value: 1 },
  { label: '1 天', value: 24 },
  { label: '7 天（默认）', value: 168 },
  { label: '30 天（上限）', value: 720 },
]

/** 列表里每条的状态文案 */
function stateTag(state) {
  if (state === 'active') return { type: 'success', text: '有效' }
  if (state === 'expired') return { type: 'warning', text: '已过期' }
  return { type: 'error', text: '已吊销' }
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function loadShares() {
  sharesLoading.value = true
  try {
    const res = await listShares(route.params.id)
    shares.value = res.data.items || []
  } catch (e) {
    // ⚠️ 课 32：分享列表加载失败不阻断导出,但要说一句
    //    （之前只 console.warn → 老师以为分享功能坏了）
    console.warn('分享列表加载失败:', parseError(e).message)
  } finally {
    sharesLoading.value = false
  }
}

async function doCreateShare() {
  creating.value = true
  errorMsg.value = ''
  try {
    const res = await createShare(route.params.id, expireHours.value)
    lastCreated.value = buildShareUrl(res.data.token)
    await loadShares()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `生成失败：${e.message}`
  } finally {
    creating.value = false
  }
}

async function copyLink(url) {
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    // 剪贴板 API 在非 https / 老浏览器上会失败 → 回退到选中提示
    window.prompt('复制这个链接：', url)
  }
}

async function doRevoke(shareId) {
  errorMsg.value = ''
  try {
    await revokeShare(route.params.id, shareId)
    await loadShares()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `吊销失败：${e.message}`
  }
}

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
  await loadShares()
}

onMounted(load)

async function doExportJpg() {
  exportingJpg.value = true
  errorMsg.value = ''
  try {
    const filename = await exportPaperJpg(paper.value.id, paper.value.title)
    console.log('已导出:', filename)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `导出失败：${e.message}`
  } finally {
    exportingJpg.value = false
  }
}

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
    <div class="tqb-page-head">
      <NButton size="small" quaternary @click="router.push({ name: 'papers' })">
        ← 我的试卷
      </NButton>
      <NSpace v-if="paper">
        <NButton size="small" type="primary" :loading="exporting" @click="doExport">
          导出 PDF
        </NButton>
        <NButton size="small" :loading="exportingJpg" @click="doExportJpg">
          导出 JPG
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

        <!-- === 分享链接（课 24）=== -->
        <NDivider />
        <div class="share-title">🔗 分享链接</div>
        <div class="share-hint">
          发到微信群 / 学生家长群，<b>对方不用账号</b>，点开就能看卷子、下 PDF / JPG。
          链接<b>必带过期时间</b>，也能随时吊销。
        </div>

        <NSpace align="center" style="margin-top: 10px">
          <NSelect v-model:value="expireHours" :options="EXPIRE_OPTIONS" style="width: 150px" />
          <NButton type="primary" :loading="creating" @click="doCreateShare">
            生成分享链接
          </NButton>
        </NSpace>

        <NAlert v-if="lastCreated" type="success" :bordered="false" style="margin-top: 10px">
          <div>新链接已生成：</div>
          <NInput :value="lastCreated" readonly style="margin-top: 6px" />
          <NButton size="small" style="margin-top: 8px" @click="copyLink(lastCreated)">
            复制链接
          </NButton>
        </NAlert>

        <div v-if="shares.length" style="margin-top: 12px">
          <div class="share-list-title">已生成的链接（{{ shares.length }}）</div>
          <div v-for="s in shares" :key="s.id" class="share-item">
            <div class="share-item-left">
              <NTag :type="stateTag(s.state).type" size="small" round>
                {{ stateTag(s.state).text }}
              </NTag>
              <span class="share-url">{{ buildShareUrl(s.token) }}</span>
            </div>
            <div class="share-item-meta">
              过期 {{ fmtTime(s.expires_at) }} · 打开 {{ s.view_count }} 次
              <NSpace :size="4" style="display: inline-flex; margin-left: 8px">
                <NButton size="tiny" quaternary @click="copyLink(buildShareUrl(s.token))">复制</NButton>
                <NButton
                  v-if="s.state === 'active'"
                  size="tiny"
                  quaternary
                  type="error"
                  @click="doRevoke(s.id)"
                >
                  吊销
                </NButton>
              </NSpace>
            </div>
          </div>
        </div>
        <NAlert v-else-if="!sharesLoading" type="info" :bordered="false" style="margin-top: 10px">
          还没有分享链接。
        </NAlert>
      </NCard>
    </NSpin>
  </div>
</template>

<style scoped>

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

/* === 分享链接（课 24）=== */
.share-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}

.share-hint {
  font-size: 12px;
  color: var(--tqb-text-secondary);
  line-height: 1.7;
}

.share-list-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.share-item {
  padding: 8px 0;
  border-top: 1px solid var(--tqb-border);
}

.share-item-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.share-url {
  font-size: 12px;
  color: var(--tqb-text-secondary);
  word-break: break-all;
}

.share-item-meta {
  font-size: 11px;
  color: var(--tqb-text-tertiary);
  margin-top: 4px;
  margin-left: 2px;
}
</style>
