<script setup>
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import axios from 'axios'
import {
  NCard, NSpace, NButton, NTag, NTabs, NTabPane,
  NSpin, NAlert, NEmpty, NImage, NText,
} from 'naive-ui'

// === Props:由 UploadImage 上传成功后回传 ===
const props = defineProps({
  imageUrl: { type: String, default: '' },  // 例: /uploads/xxx.jpg
})

// === 状态 ===
const taskId = ref(null)
const status = ref('idle')      // idle / processing / completed / failed
const result = ref(null)        // PaddleOCR blocks + stats
const error = ref(null)
let pollTimer = null

// === 计算属性 ===
const textBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'text') ?? []
)
const formulaBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'formula') ?? []
)
const tableBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'table') ?? []
)

// === 开始 OCR ===
async function startOcr() {
  if (!props.imageUrl) {
    error.value = 'image_url 为空'
    return
  }
  status.value = 'processing'
  error.value = null
  result.value = null
  
  try {
    const res = await axios.post('http://localhost:8000/api/ocr/', {
      image_url: props.imageUrl,
    })
    taskId.value = res.data.task_id
    startPolling()
  } catch (e) {
    status.value = 'failed'
    error.value = `启动失败: ${e.response?.data?.detail || e.message}`
  }
}

// === 轮询状态 ===
function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const res = await axios.get(`http://localhost:8000/api/ocr/status/${taskId.value}`)
      const data = res.data
      
      if (data.status === 'completed') {
        status.value = 'completed'
        result.value = data.result
        stopPolling()
      } else if (data.status === 'failed') {
        status.value = 'failed'
        error.value = data.error || 'OCR 识别失败'
        stopPolling()
      }
      // processing 继续轮询
    } catch (e) {
      status.value = 'failed'
      error.value = `轮询失败: ${e.message}`
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(stopPolling)

// === 渲染 Markdown(MVP:简单拼接 text blocks;lesson-07 接 KaTeX 渲染公式)===
const plainText = computed(() =>
  textBlocks.value.map(b => b.text).join('\n')
)

const withFormulas = computed(() =>
  result.value?.blocks
    .filter(b => b.type === 'text' || b.type === 'formula')
    .map(b => b.type === 'formula' ? `$${b.latex}$` : b.text)
    .join('\n') ?? ''
)

// === 一键复制 ===
async function copyMarkdown() {
  await navigator.clipboard.writeText(withFormulas.value)
  // 提示用户已复制(lesson-31 UI 美化时换 NMessage)
  alert('已复制 Markdown 到剪贴板')
}
</script>

<template>
  <NCard title="🔍 OCR 识别结果" size="small">
    <NSpace vertical size="medium">
      <!-- 顶部:状态 + 原图 -->
      <NSpace align="center">
        <NTag :type="status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'info'">
          {{ status === 'idle' ? '待识别' : status === 'processing' ? '识别中...' : status === 'completed' ? '已完成' : '失败' }}
        </NTag>
        <NImage
          v-if="imageUrl"
          :src="`http://localhost:8000${imageUrl}`"
          width="80"
          height="80"
          object-fit="cover"
          style="border-radius: 4px"
        />
        <NButton type="primary" :disabled="status === 'processing' || !imageUrl" @click="startOcr">
          {{ status === 'completed' ? '🔄 重新识别' : '🚀 开始识别' }}
        </NButton>
      </NSpace>

      <!-- 错误 -->
      <NAlert v-if="error" type="error" :show-icon="false">❌ {{ error }}</NAlert>

      <!-- Loading -->
      <NSpin v-if="status === 'processing'" size="medium">
        <NEmpty description="PaddleOCR 正在识别(平均 5 秒)..." />
      </NSpin>

      <!-- 结果:三 tab -->
      <NTabs v-if="status === 'completed'" type="line" animated>
        <NTabPane name="text" tab="① 纯文本">
          <pre style="white-space: pre-wrap; font-family: system-ui">{{ plainText }}</pre>
          <NText depth="3" style="font-size: 12px">
            共 {{ textBlocks.length }} 个文本块 · {{ result?.stats?.elapsed_ms }}ms · {{ result?.stats?.model }}
          </NText>
        </NTabPane>
        <NTabPane name="formula" tab="② 带公式(Markdown)">
          <pre style="white-space: pre-wrap; font-family: monospace">{{ withFormulas }}</pre>
          <NSpace>
            <NButton size="small" @click="copyMarkdown">📋 复制 Markdown</NButton>
            <NText depth="3" style="font-size: 12px">
              {{ formulaBlocks.length }} 个公式块(lesson-07 接 KaTeX 渲染)
            </NText>
          </NSpace>
        </NTabPane>
        <NTabPane name="table" tab="③ 结构(含表格)">
          <div v-for="(b, i) in result?.blocks" :key="i">
            <div v-if="b.type === 'text'">{{ b.text }}</div>
            <div v-else-if="b.type === 'formula'" style="font-family: monospace; color: #18a058">
              {{ b.latex }}
            </div>
            <div v-else-if="b.type === 'table'" v-html="b.html" />
          </div>
        </NTabPane>
      </NTabs>
    </NSpace>
  </NCard>
</template>