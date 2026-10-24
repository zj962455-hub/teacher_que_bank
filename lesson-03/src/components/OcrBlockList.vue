<script setup>
/**
 * OcrBlockList — OCR block 列表（lesson-06 任务 4 抽取）
 *
 * 为什么抽出来
 * ------------
 * 「① 纯文本」和「③ 结构」两个 tab 的 block 列表代码几乎完全一样
 * （都是 v-for + hover 绑定 + active 态），只有内容渲染方式不同：
 *   - simple：type 标签 + 文本 + 置信度（给人快速扫读用）
 *   - rich  ：按 type 分别渲染 text / formula / table（给人看结构用）
 *
 * 第三处需要用到时（任务 5 的编辑器预览、lesson-07 的 KaTeX）就直接复用，
 * 不再复制第三遍。
 *
 * 为什么要 hoverIndex 往下传（受控组件）
 * ---------------------------------------
 * OcrResult.vue 里 hover 的不是「当前 tab 内的下标」，而是 **allBlocks 的全局下标**
 * —— 因为高亮框要画在原图上，而 bbox 是 PaddleOCR 按原图顺序返回的，
 * 用 tab 内下标会错位（比如 tab1 的第 0 块和 tab3 的第 0 块不是同一个 block）。
 *
 * 受控的好处：子组件只负责「告诉父组件我 hover 了谁」，不自己存 hover 状态。
 * 这样 tab 切换时 hover 不会因为下标含义不同而错乱，父组件永远是唯一真相源。
 */
import { ref, computed } from 'vue'
import { NTag, NText } from 'naive-ui'
import { renderLatex, renderMathText } from '../utils/mathRenderer'

// === Props ===
const props = defineProps({
  // block 数组（必须是 result.blocks 原数组，不能是 filter 后的子集）
  blocks: { type: Array, default: () => [] },

  // 渲染模式：simple = type 标签 + 文本；rich = 按 type 分别渲染
  renderMode: {
    type: String,
    default: 'simple',
    validator: v => ['simple', 'rich'].includes(v),
  },

  // 受控：当前 hover 的全局下标，-1 表示没 hover
  hoverIndex: { type: Number, default: -1 },

  // 列表最大高度（px），超出滚动
  maxHeight: { type: Number, default: 360 },
})

// === Emits：把 hover 事件抛给父组件 ===
const emit = defineEmits(['hover'])

/**
 * 找到 block 在 blocks 数组里的**全局下标**
 * 不用 v-for 的 (item, i)，因为 v-for 的 i 是「当前遍历的数组下标」——
 * 这里虽然 blocks 就是全量数组，但显式用 indexOf 更清晰，
 * 而且未来如果传进来的是 filter 过的子集，indexOf 依然能找到正确的全局位置。
 */
function globalIndexOf(block) {
  return props.blocks.indexOf(block)
}

/** hover 进入时告诉父组件「全局第几块被 hover 了」 */
function onEnter(block) {
  emit('hover', globalIndexOf(block))
}

/** hover 离开时清空（-1） */
function onLeave() {
  emit('hover', -1)
}

/**
 * 渲染每个 block 的内容（lesson-07 KaTeX）
 * ------------------------------------------------
 * - type=formula → 块级 KaTeX 渲染
 * - type=text    → 文本里内嵌的 $...$ 混排渲染
 * - type=table   → PaddleOCR 的 HTML 表格，原样
 *
 * 为什么要放 computed 而不在 template 里 v-if
 * --------------------------------------------
 * KaTeX 每次渲染都要 parse LaTeX，有开销。
 * 放 computed 里能吃到 Vue 的缓存 —— 父组件 hover 状态变化时，
 * 这个 computed 不会重算（依赖没变），公式不会反复重渲染。
 *
 * ⚠️ 坑：v-for 的第二个参数别叫 indexOf
 * ------------------------------------
 * Vue 模板编译后的作用域里，indexOf 会跟 Array.prototype.indexOf 撞名，
 * 运行时报 "indexOf is not a function"（2026-10-24 实测踩到）。
 * 这里用 blockIndex。
 */
const renderedContent = computed(() => {
  return props.blocks.map(b => {
    if (b.type === 'formula') {
      return { html: renderLatex(b.latex, true), isFormula: true }
    }
    if (b.type === 'table') {
      return { html: b.html || '', isFormula: false }
    }
    return { html: renderMathText(b.text || ''), isFormula: false }
  })
})
</script>

<template>
  <div :style="{ maxHeight: `${maxHeight}px`, overflowY: 'auto' }">
    <div
      v-for="(b, blockIndex) in blocks"
      :key="globalIndexOf(b)"
      class="ocr-block"
      :class="{ active: globalIndexOf(b) === hoverIndex }"
      @mouseenter="onEnter(b)"
      @mouseleave="onLeave"
    >
      <!-- ===== simple 模式：type 标签 + 渲染内容 + 置信度 ===== -->
      <template v-if="renderMode === 'simple'">
        <NTag
          size="small"
          :bordered="false"
          :type="b.type === 'text' ? 'default' : b.type === 'formula' ? 'success' : 'warning'"
        >
          {{ b.type }}
        </NTag>
        <!-- KaTeX 渲染输出（v-html） -->
        <span
          class="ocr-block-content"
          :class="{ 'is-formula': b.type === 'formula' }"
          v-html="renderedContent[blockIndex]?.html"
        />
        <NText depth="3" style="font-size: 11px; margin-left: 6px;">
          {{ Math.round(b.confidence * 100) }}%
        </NText>
      </template>

      <!-- ===== rich 模式：按 type 分别渲染 ===== -->
      <template v-else>
        <div
          class="ocr-block-content"
          :class="{ 'is-formula': b.type === 'formula' }"
          v-html="renderedContent[blockIndex]?.html"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
/*
 * 样式从 OcrResult.vue 搬过来了（用 scoped，两边互不影响）
 * 之所以要搬：如果父组件的 scoped 样式不会作用到子组件的 DOM 上，
 * 抽出来的组件必须自己带一份，否则 hover 样式全丢。
 */
.ocr-block {
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
  margin-bottom: 4px;
  transition: background 0.1s;
}
.ocr-block:hover,
.ocr-block.active {
  background: rgba(24, 160, 88, 0.08);
  border-color: rgba(24, 160, 88, 0.3);
}

/* 渲染内容容器 */
.ocr-block-content {
  font-size: 13px;
  margin-left: 6px;
  display: inline-block;
  vertical-align: middle;
}

/* 公式块：独占一行居中 */
.ocr-block-content.is-formula {
  display: block;
  margin: 6px 0;
  text-align: center;
}

/* KaTeX 输出的字体在 macOS 上要显式指定，否则会掉回默认字体 */
.ocr-block-content :deep(.katex) {
  font-size: 1.05em;
}
</style>