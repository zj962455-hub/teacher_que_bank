<script setup>
import { ref, computed, onMounted } from 'vue'
import AppIcon from './AppIcon.vue'
import { http, fetchImageBlobUrl } from '../api/auth'
import { parseError } from '../utils/errors'   // ← 课 32:统一错误解析
import { useAsyncTask } from '../composables/useAsyncTask'

// === 事件 ===
// ⚠️ lesson-35：上传成功后必须 emit —— CapturePage 靠它把图片交给 OCR 面板。
//    以前从来没 emit 过 → CapturePage 的 currentImage 永远是空 →
//    OcrResult 的「开始识别」按钮 :disabled="... || !imageUrl" 永远为 true
//    → 老师连「开始识别」都点不动。
//    参数是后端返回的 url（/api/uploads/<filename>），不是本地拼的路径。
const emit = defineEmits(['uploaded'])

// === 状态 ===
const fileList = ref([])              // 用户选的 File 数组
const previews = ref([])              // 预览数组 [{file, dataUrl}]
const uploadedList = ref([])          // 上传结果数组
const progress = computed(() => {
  if (fileList.value.length === 0) return 0
  return Math.round(uploadedList.value.length / fileList.value.length * 100)
})
const localError = ref('')            // 本地校验错误(还没发请求就没了的那种)
const warning = ref(null)             // 文件超限等非阻断提示
const MAX_SIZE = 5 * 1024 * 1024      // 文件大小限制 5 MB
const isDragging = ref(false)         // 拖入状态(用于视觉反馈)
const historyList = ref([])           // 上传历史(简易画廊)
// 图片的 blob URL 映射(filename → blob: URL)
const imageUrls = ref({})            // ⚠️ 图片接口要鉴权，<img src> 带不了 Authorization 头
const blobUrls = []                  // 记下来以便卸载时 revoke

// === 加载图片的 blob URL（带 token） ===
async function loadImageUrl(url) {
  if (!url || imageUrls.value[url]) return imageUrls.value[url]
  try {
    const blobUrl = await fetchImageBlobUrl(url)
    blobUrls.push(blobUrl)
    imageUrls.value = { ...imageUrls.value, [url]: blobUrl }
    return blobUrl
  } catch (e) {
    // ⚠️ 课 32：图片加载失败不致命（可能还没上传），但要记清楚
    console.warn('图片加载失败:', url, parseError(e).message)
    return ''
  }
}

// 历史图鉴的图逐张加载（拿到列表后并行转 blob）
async function loadHistoryImages(list) {
  await Promise.all(list.map((item) => loadImageUrl(item.url)))
}

// === 选文件后立刻预览 ===
function onFilesChange(e) {
  const selectedFiles = Array.from(e.target.files)
  if (selectedFiles.length === 0) return

  // === 大小预校验:超限的跳过 ===
  const accepted = []
  const skipped = []
  for (const f of selectedFiles) {
    if (f.size > MAX_SIZE) {
      skipped.push(`${f.name} (${Math.round(f.size / 1024 / 1024)} MB)`)
    } else {
      accepted.push(f)
    }
  }
  
  // 全部超限
  if (accepted.length === 0) {
    warning.value = null
    localError.value = `${selectedFiles.length} 个文件全部超过 5 MB 限制,已拒绝:\n${skipped.join('\n')}`
    fileList.value = []
    previews.value = []
    return
  }
  
  // 部分超限
  if (skipped.length > 0) {
    warning.value = `已跳过 ${skipped.length} 个超过 5 MB 的文件:${skipped.join(', ')}`
  } else {
    warning.value = null
  }
  localError.value = null
  
  fileList.value = accepted
  uploadedList.value = []
  previews.value = []
  
  accepted.forEach((f) => {
    const reader = new FileReader()
    reader.onload = (ev) => {
      previews.value.push({ file: f, dataUrl: ev.target.result })
    }
    reader.readAsDataURL(f)
  })
}

// === 拖拽 ===
function onDrop(e) {
  isDragging.value = false
  // 复用 onFilesChange:把 dataTransfer.files 包装成 input.files 一样的结构
  onFilesChange({ target: { files: e.dataTransfer.files } })
}

// === 上传到后端 ===
// ⚠️ 用 allSettled 而不是 all —— 一个文件失败不该把其他成功的也抹掉。
//    老师的场景是「一次拍好几页」，第 3 页失败不该让前 2 页白传。
async function uploadFiles() {
  const files = fileList.value

  const results = await Promise.allSettled(
    files.map((f) => {
      const formData = new FormData()
      formData.append('file', f)
      return http.post(
        '/uploads/',
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 30000,
          // 总进度由 computed 自动算,不更新 progress
        }
      )
    })
  )

  const ok = results.filter((r) => r.status === 'fulfilled').map((r) => r.value.data)
  const failed = results.filter((r) => r.status === 'rejected')

  uploadedList.value = ok

  // 图片要带 token 才能读 → 转成 blob URL
  await loadHistoryImages(ok)

  // ⚠️ lesson-35：emit **所有**成功的 url（数组）
  //    以前只 emit 最后一张 —— 老师一次传 4 张，只有 1 张进了 OCR 面板，
  //    另外 3 张压根没发起识别，看着就像「识别不出来」。
  //    现在全部交给父组件，由它排队一张张识别。
  if (ok.length > 0) {
    emit('uploaded', ok.map(item => item.url))
  }

  if (failed.length > 0) {
    const reasons = failed.map((r) => parseError(r.reason).message).join('; ')
    if (ok.length === 0) {
      // 全失败 → 抛给 useAsyncTask 统一处理（错误提示走 parseError）
      throw parseError(failed[0].reason)
    }
    // 部分失败 → 成功的照用,失败的给个非阻断提示
    warning.value = `${failed.length} 个文件上传失败:${reasons}`
  }

  // 刷新历史画廊
  await runHistory().catch(() => undefined)

  return ok
}

// === 上传任务（统一 loading / error）===
const {
  loading: uploading,
  error: uploadError,
  run: runUpload,
  clearError: clearUploadError,
} = useAsyncTask(uploadFiles)

function upload() {
  localError.value = ''
  clearUploadError()
  if (fileList.value.length === 0) {
    localError.value = '请先选文件'
    return
  }
  uploadedList.value = []
  warning.value = null
  return runUpload().catch(() => undefined)
}

// === 加载历史 ===
async function fetchHistory() {
  const res = await http.get('/uploads/list')
  historyList.value = res.data
  // 逐张转成带鉴权的 blob URL
  await loadHistoryImages(res.data)
  return res.data
}

const { loading: historyLoading, error: historyError, run: runHistory } = useAsyncTask(fetchHistory)
const loadingHistory = computed(() => historyLoading.value)

// 刷新历史画廊（按钮用）
function refreshHistory() {
  return runHistory().catch(() => undefined)
}

// 错误提示统一出口：本地校验 + 上传 + 历史加载
const error = computed(() =>
  localError.value || uploadError.value?.message || historyError.value?.message || ''
)

onMounted(() => {
  runHistory().catch(() => undefined)
})

// === 重置 ===
function reset() {
  fileList.value = []
  previews.value = []
  uploadedList.value = []
  localError.value = ''
  warning.value = null
  clearUploadError()
}
</script>

<template>
  <div class="upload-image">
    <div class="upload-head">
      <h3 class="tqb-section-title">
        <AppIcon name="upload" :size="16" />
        上传题目图片
      </h3>
      <span class="upload-limit">单个文件 ≤ 5 MB</span>
    </div>

    <!-- 拖拽区：真实的 file input 透明铺满整块区域，点哪都能选文件 -->
    <div
      class="dropzone"
      :class="{ dragging: isDragging }"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
    >
      <input
        type="file"
        accept="image/*"
        multiple
        class="dropzone-input"
        data-testid="file-input"
        @change="onFilesChange"
      />
      <span class="dropzone-icon"><AppIcon name="image" :size="24" /></span>
      <p class="dropzone-title">把题目图片拖到这里</p>
      <p class="dropzone-hint">也可以直接点这块区域选文件，一次可多选</p>
      <span class="dropzone-chip">
        <AppIcon name="upload" :size="15" />
        选择文件
      </span>
      <span v-if="fileList.length > 0" class="dropzone-count">已选 {{ fileList.length }} 张</span>
    </div>

    <!-- 预览（选完立刻显示，还没上传）-->
    <div v-if="previews.length > 0" class="preview">
      <h4 class="preview-title">预览 · {{ previews.length }} 张</h4>
      <div class="preview-grid">
        <div v-for="(p, i) in previews" :key="i" class="preview-item">
          <img :src="p.dataUrl" :alt="'预览 ' + (i + 1)" />
          <p class="preview-name" :title="p.file.name">{{ p.file.name }}</p>
          <p class="preview-size">{{ Math.round(p.file.size / 1024) }} KB</p>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="actions">
      <div v-if="uploading" class="progress">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progress + '%' }" />
        </div>
        <span class="progress-text">上传中 {{ progress }}%（{{ uploadedList.length }}/{{ fileList.length }}）</span>
      </div>
      <button
        type="button"
        @click="upload"
        :disabled="fileList.length === 0 || uploading"
        class="btn btn--primary"
      >
        <AppIcon name="upload" :size="15" />
        {{ uploading ? '上传中…' : '上传 ' + fileList.length + ' 张' }}
      </button>
      <button v-if="fileList.length > 0" type="button" @click="reset" class="btn btn--ghost">
        <AppIcon name="refresh" :size="15" />
        重置
      </button>
    </div>

    <div v-if="warning" class="notice notice--warning">{{ warning }}</div>
    <div v-if="error" class="notice notice--error">{{ error }}</div>

    <!-- 上传成功 -->
    <div v-if="uploadedList.length > 0" class="uploaded">
      <h4 class="preview-title">已上传 {{ uploadedList.length }} 张</h4>
      <div class="preview-grid">
        <div v-for="(u, i) in uploadedList" :key="i" class="preview-item">
          <img :src="imageUrls[u.url] || ''" :alt="'已上传 ' + (i + 1)" />
          <p class="preview-name upload-url" :title="u.url">{{ u.url }}</p>
        </div>
      </div>
    </div>
  </div>

  <!-- 历史画廊 -->
  <div class="history">
    <div class="history-header">
      <h3 class="tqb-section-title">
        <AppIcon name="clock" :size="16" />
        历史图片（{{ historyList.length }}）
      </h3>
      <button type="button" @click="refreshHistory" :disabled="loadingHistory" class="btn btn--ghost">
        <AppIcon name="refresh" :size="15" />
        {{ loadingHistory ? '加载中…' : '刷新' }}
      </button>
    </div>
    <p v-if="historyList.length === 0" class="history-empty">暂无上传记录</p>
    <div v-else class="history-grid">
      <div v-for="h in historyList" :key="h.filename" class="history-item">
        <img :src="imageUrls[h.url] || ''" :alt="h.original_name || h.filename" />
        <p class="history-filename" :title="h.original_name || h.filename">{{ h.filename }}</p>
      </div>
    </div>
  </div>
</template>


<style scoped>
/**
 * 上传区样式 —— 全部走设计令牌
 *
 * 之前这个组件是整套界面里唯一没接令牌的地方：
 * 绿色 #42b883（跟全站靛蓝主色完全不是一套）、#ddd 边框、#999 文字，
 * 还直接把原生 <input type="file"> 露出来（浏览器默认按钮丑到无法统一）。
 * 现在：颜色全部 var(--tqb-*)，原生 input 透明铺满拖拽区，键盘也能用。
 */
.upload-image {
  padding: var(--tqb-space-5);
  background: var(--tqb-bg-card);
  border: 1px solid transparent;
  border-radius: var(--tqb-radius-lg);
  box-shadow: var(--tqb-shadow-card);
}

.upload-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--tqb-space-3);
  margin-bottom: var(--tqb-space-4);
}

.upload-limit {
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-tertiary);
}

/* 拖拽区 */
.dropzone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--tqb-space-2);
  padding: var(--tqb-space-8) var(--tqb-space-4);
  border: 1px dashed var(--tqb-border-strong);
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-surface-muted);
  text-align: center;
  transition: border-color var(--tqb-transition), background var(--tqb-transition);
}

/* 原生 input 透明铺满整块区域：点哪都能选文件，键盘 Tab 也能到 */
.dropzone-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.dropzone:focus-within {
  box-shadow: var(--tqb-focus-ring);
}

.dropzone.dragging {
  border-color: var(--tqb-primary);
  background: var(--tqb-primary-soft);
}

.dropzone-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-bg-card);
  color: var(--tqb-primary);
}

.dropzone-title {
  margin: 0;
  font-size: var(--tqb-font-md);
  font-weight: 600;
  color: var(--tqb-text-primary);
}

.dropzone-hint {
  margin: 0;
  font-size: var(--tqb-font-sm);
  color: var(--tqb-text-secondary);
}

.dropzone-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--tqb-space-2);
  margin-top: var(--tqb-space-2);
  padding: var(--tqb-space-2) var(--tqb-space-4);
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-primary);
  color: var(--tqb-text-inverse);
  font-size: var(--tqb-font-base);
  font-weight: 500;
  pointer-events: none;
}

.dropzone-count {
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-tertiary);
}

/* 预览 / 已上传 */
.preview,
.uploaded {
  margin-top: var(--tqb-space-5);
}

.preview-title {
  margin: 0 0 var(--tqb-space-3);
  font-size: var(--tqb-font-sm);
  font-weight: 600;
  color: var(--tqb-text-regular);
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--tqb-space-3);
}

.preview-item {
  padding: var(--tqb-space-2);
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-surface-muted);
}

.preview-item img {
  width: 100%;
  height: 96px;
  object-fit: cover;
  border-radius: var(--tqb-radius-sm);
  /* 图片描边用纯黑/白，避免在图边留一圈彩色毛边 */
  outline: 1px solid rgba(0, 0, 0, 0.1);
  outline-offset: -1px;
  background: var(--tqb-bg-card);
}

.preview-name {
  margin: var(--tqb-space-2) 0 0;
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-size {
  margin: 2px 0 0;
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.upload-url {
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
}

/* 操作按钮 */
.actions {
  display: flex;
  align-items: center;
  gap: var(--tqb-space-3);
  margin-top: var(--tqb-space-4);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--tqb-space-2);
  height: 34px;
  padding: 0 var(--tqb-space-4);
  border: 1px solid transparent;
  border-radius: var(--tqb-radius-md);
  font-family: inherit;
  font-size: var(--tqb-font-base);
  font-weight: 500;
  cursor: pointer;
  transition: background var(--tqb-transition), color var(--tqb-transition),
    box-shadow var(--tqb-transition);
}

.btn--primary {
  background: var(--tqb-primary);
  color: var(--tqb-text-inverse);
}

.btn--primary:hover:not(:disabled) {
  background: var(--tqb-primary-hover);
}

.btn--primary:disabled {
  background: var(--tqb-surface-sunken);
  color: var(--tqb-text-tertiary);
  cursor: not-allowed;
}

.btn--ghost {
  background: var(--tqb-surface-muted);
  color: var(--tqb-text-regular);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--tqb-bg-hover);
  color: var(--tqb-text-primary);
}

.btn--ghost:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 进度 */
.progress {
  display: flex;
  align-items: center;
  gap: var(--tqb-space-3);
  flex: 1 1 260px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: var(--tqb-radius-full);
  background: var(--tqb-surface-sunken);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--tqb-radius-full);
  background: var(--tqb-primary);
  transition: width var(--tqb-transition);
}

.progress-text {
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-secondary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* 提示 */
.notice {
  margin-top: var(--tqb-space-3);
  padding: var(--tqb-space-3) var(--tqb-space-4);
  border-radius: var(--tqb-radius-md);
  font-size: var(--tqb-font-sm);
  white-space: pre-line;
}

.notice--warning {
  background: var(--tqb-warning-soft);
  color: var(--tqb-warning);
}

.notice--error {
  background: var(--tqb-danger-soft);
  color: var(--tqb-danger);
}

/* 历史画廊 */
.history {
  margin-top: var(--tqb-space-5);
  padding-top: var(--tqb-space-5);
  border-top: 1px solid var(--tqb-border);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--tqb-space-3);
  margin-bottom: var(--tqb-space-4);
}

.history-empty {
  margin: 0;
  padding: var(--tqb-space-6);
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-surface-muted);
  color: var(--tqb-text-tertiary);
  font-size: var(--tqb-font-sm);
  text-align: center;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--tqb-space-3);
}

.history-item {
  padding: var(--tqb-space-2);
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-surface-muted);
  text-align: center;
}

.history-item img {
  width: 100%;
  height: 96px;
  object-fit: cover;
  border-radius: var(--tqb-radius-sm);
  outline: 1px solid rgba(0, 0, 0, 0.1);
  outline-offset: -1px;
  background: var(--tqb-bg-card);
}

.history-filename {
  margin: var(--tqb-space-2) 0 0;
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
