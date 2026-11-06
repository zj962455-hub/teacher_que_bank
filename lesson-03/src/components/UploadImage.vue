<script setup>
import { ref, computed, onMounted } from 'vue'
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

  // ⚠️ lesson-35：emit **最后一个成功的** url
  //    多个文件时，老师在 OCR 面板看的是哪张图就对哪张 ——
  //    最后一次成功的那张是老师最可能想识别的那张。
  if (ok.length > 0) {
    emit('uploaded', ok[ok.length - 1].url)
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
    <h2>📤 上传题目图片</h2>
    
    <!-- 文件选择器 + 拖拽区 -->
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
          @change="onFilesChange"
          data-testid="file-input"
        />
        <span v-if="fileList.length > 0" class="filename">
          {{ fileList.length }} 个文件已选
        </span>
        <p class="dropzone-hint">📂 拖拽图片到此处,或点击选择文件</p>
    </div>
    
    <!-- 预览(选完立刻显示,没上传) -->
    <div v-if="previews.length > 0" class="preview">
      <h4>📋 预览:</h4>
      <div v-for="(p, i) in previews" :key="i" class="preview-item">
        <img :src="p.dataUrl" :alt="`预览 ${i+1}`" />
        <p class="preview-name">{{ p.file.name }} ({{ Math.round(p.file.size / 1024) }} KB)</p>
        </div>
    </div>
    
    <!-- 操作按钮 -->
    <div class="actions">
        <!-- 进度条(上传中显示) -->
      <div v-if="uploading" class="progress-bar">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        <span class="progress-text">⏳ 上传中 {{ progress }}% ({{ uploadedList.length }}/{{ fileList.length }})</span>
      </div>
      <button 
        @click="upload" 
        :disabled="fileList.length === 0 || uploading"
        class="primary"
      >
        {{ uploading ? '⏳ 上传中...' : `📤 上传 ${fileList.length} 张` }}
      </button>
      <button v-if="fileList.length > 0" @click="reset" class="secondary">
        ↻ 重置
      </button>
    </div>
    
    <!-- 大小警告(非阻断) -->
    <div v-if="warning" class="warning">⚠️ {{ warning }}</div>

    <!-- 错误 -->
    <div v-if="error" class="error">❌ {{ error }}</div>
    
    <!-- 上传成功 -->
    <div v-if="uploadedList.length > 0" class="uploaded">
      <h4>✅ 已上传 {{ uploadedList.length }} 张:</h4>
        <div v-for="(u, i) in uploadedList" :key="i" class="uploaded-item">
          <img :src="imageUrls[u.url] || ''" :alt="`已上传 ${i+1}`" />
          <p class="url">URL: <code>{{ u.url }}</code></p>
        </div>
    </div>
  </div>

  <!-- 历史画廊 -->
  <div class="history">
    <div class="history-header">
      <h3>📚 历史图片 ({{ historyList.length }})</h3>
      <button @click="refreshHistory" :disabled="loadingHistory" class="secondary">
        {{ loadingHistory ? '⏳ 加载中...' : '🔄 刷新' }}
      </button>
    </div>
    <div v-if="historyList.length === 0" class="history-empty">
      暂无上传记录
    </div>
    <div v-else class="history-grid">
      <div v-for="h in historyList" :key="h.filename" class="history-item">
        <img :src="imageUrls[h.url] || ''" :alt="h.original_name || h.filename" />
        <p class="history-filename">{{ h.filename }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-image { padding: 16px; border: 1px solid #ddd; border-radius: 8px; margin-top: 16px; }
.file-input { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.filename { color: #666; font-size: 14px; }
.preview, .uploaded { margin: 16px 0; }
.preview img, .uploaded img { 
  max-width: 400px; max-height: 300px; 
  border: 1px solid #ddd; border-radius: 4px;
}
.actions { display: flex; gap: 8px; margin-top: 16px; }
button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
button.primary { background: #42b883; color: white; }
button.primary:disabled { background: #ccc; cursor: not-allowed; }
button.secondary { background: #eee; color: #333; }
.error { color: #c00; margin-top: 12px; }
.url code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
.progress-bar {
  width: 100%; max-width: 300px;
  height: 24px;
  background: #f0f0f0;
  border-radius: 12px;
  overflow: hidden;
  position: relative;
  margin-bottom: 8px;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #42b883, #35495e);
  transition: width 0.2s;
}
.progress-text {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  font-size: 12px;
  color: #fff;
  font-weight: bold;
  text-shadow: 0 0 2px rgba(0,0,0,0.3);
}
.preview-item, .uploaded-item {
  display: inline-block;
  margin: 8px;
  vertical-align: top;
}
.preview-name {
  font-size: 12px;
  color: #666;
  margin: 4px 0;
}
.warning {
  color: #c80;
  background: #fffbe6;
  padding: 8px 12px;
  border-radius: 4px;
  margin-top: 12px;
  font-size: 14px;
  white-space: pre-line;
}
.dropzone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s ease;
  background: transparent;
}
.dropzone.dragging {
  border-color: #42b883;
  background: #f0f9f6;
}
.dropzone-hint {
  font-size: 13px;
  color: #999;
margin: 8px 0 0;
}
.history {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.history-header h3 {
  margin: 0;
  font-size: 16px;
}
.history-empty {
  color: #999;
  font-size: 14px;
  padding: 16px;
  text-align: center;
}
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}
.history-item {
  text-align: center;
}
.history-item img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border: 1px solid #ddd;
  border-radius: 4px;
}
.history-filename {
  font-size: 11px;
  color: #666;
  margin: 4px 0 0;
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>