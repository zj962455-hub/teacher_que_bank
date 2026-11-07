<script setup>
/**
 * CapturePage — ④ 新建题目(录题)
 *
 * 原型：题干富文本 + 图片上传 + 分类/标签/难度
 * 现在复用 UploadImage（上传）+ OcrResult（OCR 校对入库）
 */
import { ref, nextTick } from 'vue'
import { NAlert } from 'naive-ui'
import { useRouter } from 'vue-router'
import UploadImage from '../components/UploadImage.vue'
import OcrResult from '../components/OcrResult.vue'

const router = useRouter()
const currentImage = ref('')
const ocrRef = ref(null)

// === 多张图排队识别 ===
// 老师一次传 4 张 → 4 个 OCR 任务挨个跑（强模型单张约 21 秒）。
// 以前只把最后一张交给 OCR 面板，另外 3 张永远不会被识别 ——
// 老师看到的「角符号还是不对」，其实是那两张带 ∠ 的压根没跑。
const queue = ref([])
const queuedTotal = ref(0)
const doneCount = ref(0)

function onUploaded(urls) {
  const list = Array.isArray(urls) ? urls : [urls]
  queue.value = [...list]
  queuedTotal.value = list.length
  doneCount.value = 0
  runNext()
}

async function runNext() {
  if (!queue.value.length) return
  const next = queue.value.shift()
  currentImage.value = next
  // 等 props 传到子组件再触发识别
  await nextTick()
  ocrRef.value?.startOcr()
}

function onOcrDone() {
  doneCount.value += 1
  runNext()
}
</script>

<template>
  <div>
    <div class="tqb-page-head">
      <h2 class="tqb-page-title">📷 录题</h2>
    </div>

    <p class="page-desc">
      上传题目图片 → OCR 自动识别文字和公式 → 校对后一键入库。
    </p>

    <UploadImage @uploaded="onUploaded" />

    <NAlert
      v-if="queuedTotal > 1"
      type="info"
      :bordered="false"
      style="margin: 8px 0;"
    >
      本次共 {{ queuedTotal }} 张，已识别 {{ doneCount }} 张，剩余 {{ queue.length }} 张排队中
      （强模型单张约 21 秒，当前这张完成后自动继续下一张）
    </NAlert>

    <OcrResult
      ref="ocrRef"
      v-model:image-url="currentImage"
      @ocr-done="onOcrDone"
      @question-saved="router.push({ name: 'questions' })"
    />
  </div>
</template>

<style scoped>

.page-desc {
  color: #666;
  font-size: 13px;
  margin: 0 0 16px;
}
</style>
