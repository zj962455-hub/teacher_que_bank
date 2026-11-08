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
import { NTag, NText, NInput, NButton, NSpace } from 'naive-ui'
import { renderLatex, renderMathText } from '../utils/mathRenderer'
import { detectSymbolHints, applySymbolHint } from '../utils/symbolHints'

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

  // figure 块（图形区域）的裁切预览用：原图 blob URL + 原图像素尺寸
  figureImageUrl: { type: String, default: '' },
  figureImageSize: { type: Object, default: () => ({ w: 0, h: 0 }) },

  // 图是否在列表里内联显示。
  // false = 文字流里只留一行标记，图形统一放到上方的「题图」卡片里
  // （老师反馈「图识别到了但是不显示」—— 图混在文字流末尾既不显眼也容易看漏）
  showFigure: { type: Boolean, default: true },
})

// === figure 块：按 bbox 从原图里裁出图形预览 ===
// 强模型（PP-StructureV3）会把三角形这类图形标成 figure 块并给出 bbox。
// 以前这里按「未知类型」渲染 → 出来一行空白，
// 老师看着就像「图还是没识别出来」。这里用 background 定位裁出那块区域。
function figureCropStyle(b) {
  if (!props.figureImageUrl) return null
  const bbox = b && b.bbox
  if (!bbox || bbox.length < 4) return null
  const size = props.figureImageSize || {}
  if (!size.w || !size.h) return null

  const x1 = Number(bbox[0])
  const y1 = Number(bbox[1])
  const x2 = Number(bbox[2])
  const y2 = Number(bbox[3])
  const bw = Math.max(1, x2 - x1)
  const bh = Math.max(1, y2 - y1)

  const targetW = 190
  const scale = targetW / bw
  return {
    width: targetW + 'px',
    height: Math.round(bh * scale) + 'px',
    backgroundImage: 'url(' + props.figureImageUrl + ')',
    backgroundSize: Math.round(size.w * scale) + 'px ' + Math.round(size.h * scale) + 'px',
    backgroundPosition: -Math.round(x1 * scale) + 'px ' + -Math.round(y1 * scale) + 'px',
  }
}

// === 任务 3：公式编辑态 ===
const editingIndex = ref(-1)    // 正在编辑的 block 下标，-1 = 没在编辑
const editingLatex = ref('')    // 编辑框里的 LaTeX 源码

// === Emits：把 hover 事件抛给父组件 ===
const emit = defineEmits(['hover', 'update-formula', 'update-block'])

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

// === 符号疑点（平行符号 / 角符号） ===
// 只提示 + 一键改，不静默自动替换（老师明确要求：先提示，再由老师确认）。
// 平行符号被识别成 "PE/OA" 时，给老师一个「改为 PE∥OA」的按钮。
const blockHints = computed(() =>
  props.blocks.map(b => detectSymbolHints(b))
)

/** 点提示 → 算出新 block 抛给父组件（父组件负责落到 result.blocks） */
function applyHint(blockIndex, hintIndex) {
  const b = props.blocks[blockIndex]
  const hint = blockHints.value[blockIndex]?.[hintIndex]
  if (!b || !hint) return
  const next = applySymbolHint(b, hint)
  if (next === b) return
  emit('update-block', { from: b, to: next })
}

// === 任务 3：公式编辑 ===

/** 点击公式 → 进入编辑态 */
function startEdit(index, block) {
  if (block.type !== 'formula') return
  editingIndex.value = index
  editingLatex.value = block.latex || ''
}

/** 取消编辑（不改数据） */
function cancelEdit() {
  editingIndex.value = -1
  editingLatex.value = ''
}

/** 保存编辑 → 通知父组件更新 */
function saveEdit() {
  if (editingIndex.value < 0) return
  emit('update-formula', {
    index: editingIndex.value,
    latex: editingLatex.value,
  })
  editingIndex.value = -1
  editingLatex.value = ''
}

/** 编辑框里的实时预览 */
const editPreviewHtml = computed(() => renderLatex(editingLatex.value, true))

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
      <!-- ===== 编辑态：LaTeX 源码输入 + 实时预览 ===== -->
      <div v-if="editingIndex === blockIndex" class="ocr-formula-editor">
        <NInput
          v-model:value="editingLatex"
          type="textarea"
          :rows="2"
          placeholder="LaTeX 源码，例如 x^{2} + 2x + 1"
          @keydown.meta.enter="saveEdit"
          @keydown.ctrl.enter="saveEdit"
        />
        <div class="ocr-formula-preview" v-html="editPreviewHtml" />
        <NSpace size="small">
          <NButton size="tiny" type="primary" @click="saveEdit">保存</NButton>
          <NButton size="tiny" quaternary @click="cancelEdit">取消</NButton>
          <NText depth="3" style="font-size: 11px;">⌘/Ctrl + Enter 保存</NText>
        </NSpace>
      </div>

      <!-- ===== figure 块：把图形那块从原图里裁出来显示 ===== -->
      <!-- showFigure=false 时不在文字流里重复画图（图统一在上方「题图」卡片） -->
      <div
        v-else-if="b.type === 'figure'"
        class="ocr-figure-crop"
        :style="showFigure ? (figureCropStyle(b) || {}) : {}"
      >
        <NText v-if="!showFigure" depth="3" style="font-size: 11px;">
          🖼 图形（见上方「题图」）
        </NText>
        <NText v-if="b.content" depth="3" style="font-size: 11px;">
          图内标注：{{ b.content }}
        </NText>
        <NText v-else-if="!figureCropStyle(b)" depth="3" style="font-size: 11px;">
          🖼 检测到图形区域
        </NText>
      </div>

      <!-- ===== simple 模式：type 标签 + 渲染内容 + 置信度 ===== -->
      <template v-else-if="renderMode === 'simple'">
        <NTag
          size="small"
          :bordered="false"
          :type="b.type === 'text' ? 'default' : b.type === 'formula' ? 'success' : 'warning'"
        >
          {{ b.type }}
        </NTag>
        <!-- KaTeX 渲染输出（v-html）；公式可点击进入编辑 -->
        <span
          class="ocr-block-content"
          :class="{ 'is-formula': b.type === 'formula', 'is-editable': b.type === 'formula' }"
          v-html="renderedContent[blockIndex]?.html"
          @click="startEdit(blockIndex, b)"
        />
        <NText depth="3" style="font-size: 11px; margin-left: 6px;">
          {{ Math.round(b.confidence * 100) }}%
        </NText>
      </template>

      <!-- ===== rich 模式：按 type 分别渲染 ===== -->
      <template v-else>
        <div
          class="ocr-block-content"
          :class="{ 'is-formula': b.type === 'formula', 'is-editable': b.type === 'formula' }"
          v-html="renderedContent[blockIndex]?.html"
          @click="startEdit(blockIndex, b)"
        />
      </template>

      <!-- ===== 符号疑点：只提示，一键改（不自动替换） ===== -->
      <div v-if="blockHints[blockIndex]?.length" class="ocr-hints">
        <NTag
          v-for="(h, hi) in blockHints[blockIndex]"
          :key="h.kind + hi"
          size="small"
          type="warning"
          :bordered="false"
          style="cursor: pointer;"
          @click.stop="applyHint(blockIndex, hi)"
        >
          {{ h.label }} · 点击改为 {{ h.detail }}
        </NTag>
      </div>
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

/*
 * 块布局：type 标签 · 内容 · 置信度 同一行
 * ------------------------------------------
 * ⚠️ 之前 .ocr-block-content.is-formula 用了 display:block，
 *    公式独占一行 → 后面的置信度被挤到下一行，出现"孤零零的 86%"。
 *    改成 flex 布局后三者同行，公式用 flex:1 占满剩余空间并居中。
 */
.ocr-block {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;   /* 疑点提示独占下一行 */
}

/* 符号疑点提示行 */
.ocr-hints {
  flex-basis: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}

/* 渲染内容容器 */
.ocr-block-content {
  font-size: 13px;
  min-width: 0;   /* 允许 flex 子项收缩,长内容不会撑破容器 */
}

/* 公式块：占据剩余空间并居中 */
.ocr-block-content.is-formula {
  flex: 1;
  text-align: center;
  padding: 4px 0;
}

/* KaTeX 输出的字体在 macOS 上要显式指定，否则会掉回默认字体 */
.ocr-block-content :deep(.katex) {
  font-size: 1.05em;
}

/* 公式可点击提示 */
.ocr-block-content.is-editable {
  cursor: pointer;
  border-bottom: 1px dashed rgba(24, 160, 88, 0.5);
  padding-bottom: 1px;
}
.ocr-block-content.is-editable:hover {
  background: rgba(24, 160, 88, 0.06);
}

/* 公式编辑面板 */
/* figure 块：从原图裁出来的图形预览 */
.ocr-figure-crop {
  display: inline-block;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background-repeat: no-repeat;
  background-color: #fff;
  max-width: 100%;
  overflow: hidden;
}

.ocr-formula-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 0;
}

.ocr-formula-preview {
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
  padding: 6px 10px;
  min-height: 32px;
  background: #fafafa;
  text-align: center;
}
</style>