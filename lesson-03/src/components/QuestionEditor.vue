<script setup>
/**
 * QuestionEditor — 题目编辑器（lesson-06 任务 5A+5B）
 *
 * 功能
 * ----
 * - 可编辑 textarea（Markdown / 纯文本）
 * - 实时预览
 * - 自动分类（学科 / 题型 / 年级段 / 难度）+ 手动覆盖
 * - 三种复制：纯文本 / 公式版 / 完整 JSON
 * - 重置回 OCR 原文
 *
 * 默认折叠，由 OcrResult.vue 控制展开状态
 */
import { ref, computed, watch } from 'vue'
import {
  NCard, NButton, NSpace, NTag, NSelect, NInput, NText,
  NDivider, NGrid, NGridItem,
} from 'naive-ui'
import { message } from '../composables/discreteApi'
import {
  classify,
  SUBJECT_OPTIONS, TYPE_OPTIONS, GRADE_OPTIONS, DIFFICULTY_OPTIONS,
} from '../utils/classifier'
import { renderMathText } from '../utils/mathRenderer'   // ← lesson-07:KaTeX 预览

// === Props：OCR 结果 ===
const props = defineProps({
  plainText: { type: String, default: '' },      // 纯文本（无公式）
  withFormulas: { type: String, default: '' },   // 带公式（$...$）
  blocks: { type: Array, default: () => [] },    // OCR blocks 数组
})

// === 状态 ===
// 用 discreteApi 的全局实例，而不是 useMessage()
// useMessage() 必须配合 <NMessageProvider>，而本项目没用 Provider（见 main.js 注释）
const emit = defineEmits(['close'])

// 编辑框内容
// ⚠️ 优先用 withFormulas 而不是 plainText
// ------------------------------------------
// plainText 只拼接 type=text 的 block，公式块（type=formula）会被丢掉。
// 题目里公式是核心信息（"求 f(2) 的值"没有公式就不知道要求什么），
// 所以编辑器初始内容必须用带公式版。纯文本版只给「复制纯文本」按钮单独用。
const initialContent = () => props.withFormulas || props.plainText || ''

// 编辑框内容（初始用带公式版）
const content = ref(initialContent())

// 分类结果
const meta = ref({
  subject: '未知',
  type: '未知',
  grade: '通用',
  difficulty: '简单',
  confidence: 0,
  matched: [],
})

// 用户是否手动改过分类（改过就不再被 AI 覆盖）
const manuallyEdited = ref(false)

// === OCR 结果变化时重新初始化 ===
watch(
  () => [props.plainText, props.withFormulas],
  () => {
    content.value = initialContent()
    autoClassify()
  },
  { immediate: true },
)

// === 自动分类（任务 5C）===
function autoClassify() {
  // 用纯文本分类（公式标记 $...$ 会干扰关键词匹配）
  const source = props.plainText || content.value
  const r = classify(source, props.blocks)

  meta.value = r

  if (manuallyEdited.value) {
    message.info('已保留你手动设置的分类')
    return
  }

  message.success(
    `分类完成：${r.subject} / ${r.type}（置信度 ${Math.round(r.confidence * 100)}%）`,
    { duration: 2500 }
  )
}

// === 用户手动改分类 ===
function onMetaChange(key, value) {
  manuallyEdited.value = true
  meta.value = { ...meta.value, [key]: value }
}

/** 恢复自动分类（丢弃手动改动） */
function resetMeta() {
  manuallyEdited.value = false
  autoClassify()
}

// === 预览：把 Markdown 的 $...$ 转成可读形式 ===
// === 预览（lesson-07:真正用 KaTeX 渲染）===
// 之前是简陋的 ^2 → ² 字符替换，只能处理数字幂次，
// 遇到 \frac \sqrt \sum 就完全没法看。
// 现在统一走 KaTeX，公式才是它该有的样子。
const previewHtml = computed(() => renderMathText(content.value))

// === 任务 2:拼「带公式排版的纯文本」 ===
// ------------------------------------------------------------------
// 为什么不能直接用 props.plainText？
//   plainText 是后端把 text block 的 text 拼起来的，**不含公式信息**
//   （因为公式被拆成了独立的 formula block）。
//
// 老师复制到 Word 里时想要的是：
//   已知f(x) = x² + 2x + 1
//   求f(2) 的值
// 也就是公式用 Unicode 符号（x²），不是 LaTeX（x^{2}），也不是丢掉。
//
// 公式的 plain 字段是后端算好的（latex_to_plain 的结果）。
const buildPlainText = computed(() => {
  const blocks = props.blocks || []
  if (!blocks.length) return props.plainText || ''

  return blocks
    .map(b => {
      if (b.type === 'formula') {
        // 后端已算好 plain；历史记录（没有 plain 字段）降级用 latex
        return b.plain ?? b.latex ?? ''
      }
      if (b.type === 'table') return b.html ?? ''
      return b.text ?? ''
    })
    .filter(Boolean)
    .join('\n')
})

// === 复制功能（任务 5A）===
async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text)
    message.success(`已复制${label}到剪贴板`)
  } catch (e) {
    // clipboard API 在非 HTTPS 或权限被拒时会失败
    message.error(`复制失败：${e.message}（请检查浏览器剪贴板权限）`)
  }
}

function copyPlain() {
  // 优先用带公式排版的版本（任务 2）
  copyText(buildPlainText.value || content.value, '纯文本')
}

function copyFormula() {
  copyText(props.withFormulas || content.value, '公式版 Markdown')
}

function copyJson() {
  const payload = {
    subject: meta.value.subject,
    type: meta.value.type,
    grade: meta.value.grade,
    difficulty: meta.value.difficulty,
    // content 用纯文本版（公式是 x² 不是 x^{2}）—— 老师拿去直接用
    content: buildPlainText.value || content.value,
    // Markdown 版单独放一个字段,需要 LaTeX 语法的下游（比如导 PDF）时用
    contentMarkdown: props.withFormulas || content.value,
    original: {
      plain: props.plainText,
      withFormulas: props.withFormulas,
      blocks: props.blocks,
    },
  }
  copyText(JSON.stringify(payload, null, 2), '题目 JSON')
}

// === 重置回 OCR 原文 ===
function resetContent() {
  content.value = initialContent()
  manuallyEdited.value = false
  autoClassify()
  message.info('已重置回 OCR 原文')
}
</script>

<template>
  <NCard size="small" style="margin-top: 12px;">
    <template #header>
      <NSpace align="center" justify="space-between">
        <span>📝 题目编辑器</span>
        <NSpace>
          <NButton size="tiny" @click="emit('close')">收起</NButton>
        </NSpace>
      </NSpace>
    </template>

    <!-- === 自动分类结果 === -->
    <NGrid :cols="4" :x-gap="12" style="margin-bottom: 12px;">
      <NGridItem>
        <NSpace vertical size="small">
          <NText depth="3" style="font-size: 12px">学科</NText>
          <NSelect
            :value="meta.subject"
            :options="SUBJECT_OPTIONS"
            size="small"
            @update:value="v => onMetaChange('subject', v)"
          />
        </NSpace>
      </NGridItem>
      <NGridItem>
        <NSpace vertical size="small">
          <NText depth="3" style="font-size: 12px">题型</NText>
          <NSelect
            :value="meta.type"
            :options="TYPE_OPTIONS"
            size="small"
            @update:value="v => onMetaChange('type', v)"
          />
        </NSpace>
      </NGridItem>
      <NGridItem>
        <NSpace vertical size="small">
          <NText depth="3" style="font-size: 12px">学段</NText>
          <NSelect
            :value="meta.grade"
            :options="GRADE_OPTIONS"
            size="small"
            @update:value="v => onMetaChange('grade', v)"
          />
        </NSpace>
      </NGridItem>
      <NGridItem>
        <NSpace vertical size="small">
          <NText depth="3" style="font-size: 12px">难度</NText>
          <NSelect
            :value="meta.difficulty"
            :options="DIFFICULTY_OPTIONS"
            size="small"
            @update:value="v => onMetaChange('difficulty', v)"
          />
        </NSpace>
      </NGridItem>
    </NGrid>

    <!-- === 分类操作条 === -->
    <NSpace align="center" size="small" style="margin-bottom: 8px;">
      <NButton size="small" type="primary" @click="autoClassify">
        🤖 自动分类
      </NButton>
      <NButton size="small" @click="resetMeta" :disabled="!manuallyEdited">
        ↺ 恢复自动
      </NButton>
      <NTag size="small" :bordered="false" :type="meta.confidence > 0.5 ? 'success' : 'warning'">
        置信度 {{ Math.round(meta.confidence * 100) }}%
      </NTag>
      <NText v-if="meta.matched.length" depth="3" style="font-size: 11px;">
        命中关键词：{{ meta.matched.join('、') }}
      </NText>
      <NText v-if="manuallyEdited" depth="3" style="font-size: 11px; color: #d48806;">
        ⚠️ 已手动调整，AI 分类不会覆盖
      </NText>
    </NSpace>

    <NDivider style="margin: 8px 0;" />

    <!-- === 编辑区 + 预览区（左右分栏） === -->
    <div style="display: flex; gap: 12px; align-items: stretch;">
      <div style="flex: 1; min-width: 0;">
        <NText depth="3" style="font-size: 12px; display: block; margin-bottom: 4px;">
          ✏️ 题目内容（可直接编辑）
        </NText>
        <NInput
          v-model:value="content"
          type="textarea"
          :rows="8"
          placeholder="识别结果会填在这里，可以直接修改"
        />
      </div>

      <div style="flex: 1; min-width: 0;">
        <NText depth="3" style="font-size: 12px; display: block; margin-bottom: 4px;">
          👁 预览（$x^2$ 会转成 x²）
        </NText>
        <div
          style="
            border: 1px solid #d9d9d9;
            border-radius: 4px;
            padding: 8px 12px;
            min-height: 180px;
            white-space: pre-wrap;
            font-size: 13px;
            line-height: 1.7;
            background: #fafafa;
          "
          class="editor-preview"
          v-html="previewHtml"
        ></div>
      </div>
    </div>

    <!-- === 复制按钮组（任务 5A） === -->
    <NSpace style="margin-top: 12px;">
      <NButton size="small" type="primary" @click="copyPlain">
        📋 复制纯文本
      </NButton>
      <NButton size="small" @click="copyFormula">
        📐 复制公式版
      </NButton>
      <NButton size="small" @click="copyJson">
        🧩 复制 JSON
      </NButton>
      <NButton size="small" quaternary @click="resetContent">
        ↺ 重置回原文
      </NButton>
    </NSpace>
  </NCard>
</template>