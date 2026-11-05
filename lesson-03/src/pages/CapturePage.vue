<script setup>
/**
 * CapturePage — ④ 新建题目(录题)
 *
 * 原型：题干富文本 + 图片上传 + 分类/标签/难度
 * 现在复用 UploadImage（上传）+ OcrResult（OCR 校对入库）
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import UploadImage from '../components/UploadImage.vue'
import OcrResult from '../components/OcrResult.vue'

const router = useRouter()
const currentImage = ref('')

function onUploaded(url) {
  currentImage.value = url
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
    <OcrResult
      v-model:image-url="currentImage"
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
