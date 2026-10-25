<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { API_BASE, API } from '../api/config'

// === 状态 ===
const fileList = ref([])              // 用户选的 File 数组
const previews = ref([])              // 预览数组 [{file, dataUrl}]
const uploadedList = ref([])          // 上传结果数组
const uploading = ref(false)          // 上传中
const progress = computed(() => {
  if (fileList.value.length === 0) return 0
  return Math.round(uploadedList.value.length / fileList.value.length * 100)
})
const error = ref(null)               // 错误信息
const warning = ref(null)             // 文件超限等非阻断提示
const MAX_SIZE = 5 * 1024 * 1024      // 文件大小限制 5 MB
const isDragging = ref(false)         // 拖入状态(用于视觉反馈)
const historyList = ref([])           // 上传历史(简易画廊)
const loadingHistory = ref(false)     // 加载历史中

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
    error.value = `${selectedFiles.length} 个文件全部超过 5 MB 限制,已拒绝:\n${skipped.join('\n')}`
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
  error.value = null
  
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
async function upload() {
  if (fileList.value.length === 0) {
    error.value = '请先选文件'
    return
  }
  
  uploading.value = true
  error.value = null
  uploadedList.value = []
  
  try {
    // 每个文件一个请求,Promise.all 并发
    const promises = fileList.value.map((f) => {
      const formData = new FormData()
      formData.append('file', f)
      return axios.post(
        `${API}/upload/`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 30000,
          // 总进度由 computed 自动算,不更新 progress
        }
      )
    })
    
    const results = await Promise.all(promises)
    uploadedList.value = results.map((r) => r.data)
    // 刷新历史画廊
    await loadHistory()
  } catch (e) {
    error.value = `上传失败: ${e.response?.data?.detail || e.message}`
  } finally {
    uploading.value = false
  }
}

// === 加载历史 ===
async function loadHistory() {
  loadingHistory.value = true
  try {
    const res = await axios.get(`${API}/upload/list`)
    historyList.value = res.data
  } catch (e) {
    error.value = `加载历史失败: ${e.message}`
  } finally {
    loadingHistory.value = false
  }
}

onMounted(() => {
  loadHistory()
})

// === 重置 ===
function reset() {
  fileList.value = []
  previews.value = []
  uploadedList.value = []
  error.value = null
  warning.value = null
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
          <img :src="`${API_BASE}${u.url}`" :alt="`已上传 ${i+1}`" />
          <p class="url">URL: <code>{{ u.url }}</code></p>
        </div>
    </div>
  </div>

  <!-- 历史画廊 -->
  <div class="history">
    <div class="history-header">
      <h3>📚 历史图片 ({{ historyList.length }})</h3>
      <button @click="loadHistory" :disabled="loadingHistory" class="secondary">
        {{ loadingHistory ? '⏳ 加载中...' : '🔄 刷新' }}
      </button>
    </div>
    <div v-if="historyList.length === 0" class="history-empty">
      暂无上传记录
    </div>
    <div v-else class="history-grid">
      <div v-for="h in historyList" :key="h.filename" class="history-item">
        <img :src="`${API_BASE}${h.url}`" :alt="h.filename" />
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