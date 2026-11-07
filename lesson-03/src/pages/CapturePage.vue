<script setup>
/**
 * CapturePage — ④ 新建题目(录题)
 *
 * 原型：题干富文本 + 图片上传 + 分类/标签/难度
 * 现在复用 UploadImage（上传）+ OcrResult（OCR 校对入库）
 */
import { ref, nextTick } from 'vue'
import { NAlert, NSpace, NTag, NText } from 'naive-ui'
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

// 每张识别完成的图（taskId + 图片 URL）
// 以前一次传 4 张，面板只留最后一张的结果 —— 前 3 张的结果看不见、
// 容易被当成「没识别」。这里留一份清单，老师随时点回任意一张。
const doneItems = ref([])
const activeTaskId = ref('')

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

function onOcrDone(payload) {
  doneCount.value += 1
  if (payload?.status === 'completed' && payload.taskId) {
    activeTaskId.value = payload.taskId
    if (!doneItems.value.some(it => it.taskId === payload.taskId)) {
      doneItems.value = [
        ...doneItems.value,
        { taskId: payload.taskId, imageUrl: payload.imageUrl },
      ]
    }
  }
  runNext()
}

/** 翻回前面某张的识别结果（多张图之间不互相覆盖） */
function backTo(item) {
  currentImage.value = item.imageUrl
  activeTaskId.value = item.taskId
  nextTick(() => ocrRef.value?.selectHistory(item.taskId))
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

    <!-- 多张图识别完的清单：点任意一张都能翻回那次的识别结果 -->
    <NSpace v-if="doneItems.length" align="center" style="margin: 8px 0;">
      <NText depth="3" style="font-size: 12px;">已识别：</NText>
      <NTag
        v-for="(it, i) in doneItems"
        :key="it.taskId"
        size="small"
        :type="it.taskId === activeTaskId ? 'primary' : 'default'"
        style="cursor: pointer;"
        @click="backTo(it)"
      >
        第 {{ i + 1 }} 张
      </NTag>
    </NSpace>

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
