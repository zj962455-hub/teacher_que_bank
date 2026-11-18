<script setup>
/**
 * FigureThumb — 列表页的题图缩略图（lesson-35）
 *
 * 为什么要单独一个组件
 * ------------------
 * 图片接口要鉴权 → <img src="/api/uploads/xxx"> 带不了 Authorization 头
 * → 必须先取 blob 再给 <img>。列表里每行都要做这件事，
 * 塞在页面里会让 QuestionsPage 变得很乱，单独抽一个最省事。
 *
 * 缩略图很小（64×44），只为让老师一眼看出「这题有图」。
 */
import { ref, watch } from 'vue'
import { fetchImageBlobUrl } from '../api/auth'

const props = defineProps({
  path: { type: String, default: '' },
  width: { type: Number, default: 64 },
  height: { type: Number, default: 44 },
})

const blobUrl = ref('')

watch(
  () => props.path,
  async (p) => {
    blobUrl.value = ''
    if (!p) return
    try {
      blobUrl.value = await fetchImageBlobUrl(p)
    } catch (e) {
      blobUrl.value = ''
    }
  },
  { immediate: true },
)
</script>

<template>
  <div
    class="figure-thumb"
    :style="{ width: width + 'px', height: height + 'px' }"
  >
    <img v-if="blobUrl" :src="blobUrl" alt="题图" />
    <span v-else class="figure-thumb-empty">—</span>
  </div>
</template>

<style scoped>
.figure-thumb {
  border: 1px solid #e0e0e0;
  border-radius: 3px;
  background: #fafafa;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.figure-thumb img {
  max-width: 100%;
  max-height: 100%;
  display: block;
}
.figure-thumb-empty {
  color: #ccc;
  font-size: 11px;
}
</style>
