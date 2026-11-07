<script setup>
import { ref, computed, onMounted, onUnmounted, watch, h } from 'vue'
import { http, fetchImageBlobUrl } from '../api/auth'
import {
  NCard, NSpace, NButton, NTag, NTabs, NTabPane,
  NSpin, NAlert, NEmpty, NImage, NText, NSelect,
} from 'naive-ui'
import OcrBlockList from './OcrBlockList.vue'   // ← 新增:抽出的 block 列表
import QuestionEditor from './QuestionEditor.vue'   // ← 任务 5:题目编辑器
import { message } from '../composables/discreteApi'   // ← 任务 5A:全局 toast
import { stripMathMarkers } from '../utils/mathRenderer'   // ← 任务 3:更新 plain 字段
import { createQuestionFromOcr } from '../api/questions'   // ← lesson-08:一键入库
import { parseError } from '../utils/errors'   // ← 课 32:统一错误解析


// === Props:由 UploadImage 上传成功后回传 ===
const props = defineProps({
  imageUrl: { type: String, default: '' },  // 例: /api/uploads/xxx.jpg
})

// === 状态 ===
const taskId = ref(null)
// 老师在编辑器里手动改过的分类（难度等）—— 一键入库时必须带上，
// 否则后端又用 AI 的分类结果，把老师改的难度顶掉
const metaOverride = ref(null)
const status = ref('idle')      // idle / processing / completed / failed
const result = ref(null)        // PaddleOCR blocks + stats
const error = ref(null)
let pollTimer = null

// === 任务 4 新增状态 ===
const hoverIndex = ref(-1)      // 当前 hover 的 block 下标,-1 = 没 hover
const imgSize = ref({ w: 0, h: 0 })  // 原图真实像素尺寸(naturalWidth/Height)
const history = ref([])         // 历史 OCR 记录
const historyOptions = ref([])  // 下拉选项
const showEditor = ref(false)    // 任务 5:编辑器默认折叠
const saving = ref(false)         // lesson-08:入库中

// === 计算属性 ===
const allBlocks = computed(() => result.value?.blocks ?? [])

// === 题图（figure 块） ===
// 强模型会把三角形这类图形标成 figure 块并给出 bbox。
// 以前图混在文字流末尾（tab 列表最后一行），老师很容易以为「图没识别出来」。
// 这里把图形抽出来单独一张卡 —— 一眼就看到图确实在。
const figureBlocks = computed(() =>
  result.value?.blocks?.filter(b => b.type === 'figure') ?? []
)

/** 按 bbox 从原图里裁出图形（和 OcrBlockList 同一套算法） */
function figureCropStyle(b) {
  if (!imageBlobUrl.value) return null
  const bbox = b && b.bbox
  if (!bbox || bbox.length < 4) return null
  const size = imgSize.value || {}
  if (!size.w || !size.h) return null

  const x1 = Number(bbox[0])
  const y1 = Number(bbox[1])
  const x2 = Number(bbox[2])
  const y2 = Number(bbox[3])
  const bw = Math.max(1, x2 - x1)
  const bh = Math.max(1, y2 - y1)

  const targetW = 220
  const scale = targetW / bw
  return {
    width: targetW + 'px',
    height: Math.round(bh * scale) + 'px',
    backgroundImage: 'url(' + imageBlobUrl.value + ')',
    backgroundSize: Math.round(size.w * scale) + 'px ' + Math.round(size.h * scale) + 'px',
    backgroundPosition: -Math.round(x1 * scale) + 'px ' + -Math.round(y1 * scale) + 'px',
    backgroundRepeat: 'no-repeat',
    backgroundColor: '#fff',
    border: '1px solid #e0e0e0',
    borderRadius: '4px',
  }
}

const textBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'text') ?? []
)
const formulaBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'formula') ?? []
)
const tableBlocks = computed(() =>
  result.value?.blocks.filter(b => b.type === 'table') ?? []
)

// === 当前高亮的 block ===
const hoverBlock = computed(() =>
  hoverIndex.value >= 0 ? allBlocks.value[hoverIndex.value] : null
)

// === 高亮框样式:像素坐标 → 百分比(不写 JS 换算,交给 CSS 等比缩放)===
// bbox = [x1, y1, x2, y2],基于原图像素;除以原图尺寸转成百分比,
// 这样无论图片被缩放到多少,红框都精准贴合。
const highlightStyle = computed(() => {
  const b = hoverBlock.value
  const { w, h } = imgSize.value
  if (!b?.bbox || !w || !h) return { display: 'none' }

  const [x1, y1, x2, y2] = b.bbox
  return {
    left: (x1 / w * 100) + '%',
    top: (y1 / h * 100) + '%',
    width: ((x2 - x1) / w * 100) + '%',
    height: ((y2 - y1) / h * 100) + '%',
  }
})

// 图片加载完拿真实尺寸
function onImageLoad(e) {
  imgSize.value = {
    w: e.target.naturalWidth,
    h: e.target.naturalHeight,
  }
}

// === 历史记录(任务 3 的持久化成果)===
async function loadHistory() {
  try {
    const res = await http.get('/ocr/history', { params: { limit: 20 } })
    history.value = res.data.items ?? []
    historyOptions.value = history.value.map(item => {
      // 标清楚是哪个引擎 —— 强模型和轻量模型的结果差别很大，
      // 老师翻历史看到旧记录（轻量）会以为「改了也没用」
      const engine = item.result?.stats?.engine
      const engineTag = engine === 'strong' ? '强模型' : engine === 'light' ? '轻量' : ''
      return {
        label: `${engineTag ? engineTag + ' · ' : ''}${item.image_url.split('/').pop()} · ${item.created_at.slice(0, 16).replace('T', ' ')}`,
        value: item.task_id,
      }
    })
  } catch (e) {
    // 历史拉不到不影响主流程,静默即可
  }
}

// 切换历史记录:直接复用结果,不重跑 OCR
async function selectHistory(tid) {
  if (!tid) return
  const item = history.value.find(h => h.task_id === tid)
  if (!item) return

  taskId.value = item.task_id
  result.value = item.result
  status.value = item.status
  error.value = null
  hoverIndex.value = -1
  // 切历史时同步切原图
  if (item.image_url && item.image_url !== props.imageUrl) {
    emit('update:imageUrl', item.image_url)
  }
}

// 切历史要同步换图 → 需要通知父组件
const emit = defineEmits(['update:imageUrl', 'question-saved', 'ocr-done'])

// 父组件（CapturePage）用它驱动「多张图排队识别」
// selectHistory 也暴露出去 —— 多张图时老师要能翻回前面某张的结果
defineExpose({ startOcr, selectHistory })

onMounted(() => {
  loadHistory()
})

// === 原图 blob URL ===
// 图片接口要鉴权，<img src> 带不了 Authorization 头 → 用 axios 取 blob
const imageBlobUrl = ref('')

watch(
  () => props.imageUrl,
  async (url) => {
    imageBlobUrl.value = ''
    if (!url) return
    try {
      imageBlobUrl.value = await fetchImageBlobUrl(url)
    } catch (e) {
      // ⚠️ 课 32：图片加载失败不致命（可能是还没上传），但要记清楚
      console.warn('原图加载失败:', url, parseError(e).message)
    }
  },
  { immediate: true },
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
  hoverIndex.value = -1

  try {
    const res = await http.post('/ocr/', {
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
      const res = await http.get(`/ocr/status/${taskId.value}`)
      const data = res.data
      
      if (data.status === 'completed') {
        status.value = 'completed'
        result.value = data.result
        stopPolling()
        loadHistory()   // 新记录入库 → 刷下拉
        emit('ocr-done', {
          status: 'completed',
          taskId: taskId.value,
          imageUrl: props.imageUrl,
        })
      } else if (data.status === 'failed') {
        status.value = 'failed'
        error.value = data.error || 'OCR 识别失败'
        stopPolling()
        emit('ocr-done', {
          status: 'failed',
          taskId: taskId.value,
          imageUrl: props.imageUrl,
        })
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

// OCR 跑完后把新记录刷进历史下拉(任务 3 的成果)
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

// === 任务 3:公式编辑 → 更新 result 里的 latex ===
// 为什么必须往父组件的 result 写？
// -----------------------------------------
// result 是父组件持有的。子组件改了不改父组件，父组件下次重渲染就还原了。
// 而且「复制 JSON」用的也是父组件的 result —— 不同步的话复制出来的还是旧公式。
function onFormulaUpdate({ index, latex }) {
  const block = result.value?.blocks?.[index]
  if (!block) return

  block.latex = latex
  // 同步更新 plain（后端加的字段），否则复制纯文本还是旧内容
  block.plain = stripMathMarkers(latex)

  message.success('公式已更新')
}

/**
 * 符号疑点一键修改（平行符号 / 角符号）
 * 用「原对象 → 新对象」定位，不靠下标 —— 父组件的 blocks 可能是过滤过的
 */
function onBlockUpdate({ from, to }) {
  const blocks = result.value?.blocks
  if (!blocks) return
  const idx = blocks.indexOf(from)
  if (idx < 0) return
  blocks[idx] = to
  message.success('已改为：' + (to.type === 'formula' ? to.latex : to.text))
}

// === 任务 2:拼「带公式排版的纯文本」 ===
// ------------------------------------------------------------------
// withFormulas 是 Markdown 版(带 $...$ 和 ^{2}),老师复制到 Word 里不合适。
// plainText 是后端拼 text block 的,**不含公式**(公式被拆成独立 block 了)。
// 所以要自己遍历 blocks:公式用 plain 字段(后端算好的 LaTeX→Unicode),
// 文字用 text。
//
// 公式的 plain 字段来自后端 math_parser.latex_to_plain();
// 历史记录(旧数据没这字段)降级用 latex,后端已补上补算逻辑。
const buildPlainText = computed(() => {
  const blocks = result.value?.blocks ?? []
  if (!blocks.length) return plainText.value

  return blocks
    .map(b => {
      if (b.type === 'formula') return b.plain ?? b.latex ?? ''
      if (b.type === 'table') return b.html ?? ''
      return b.text ?? ''
    })
    .filter(Boolean)
    .join('\n')
})

// === lesson-08:一键入库 ===
// 后端自己从 ocr_store 读 blocks + 跑分类器,前端只传 task_id
async function saveToBank() {
  if (!taskId.value) {
    message.error('还没有识别结果')
    return
  }
  saving.value = true
  try {
    const m = metaOverride.value
    const overrides = m
      ? {
          subject: m.subject,
          question_type: m.type,
          grade: m.grade,
          difficulty: m.difficulty,
        }
      : {}
    // 把老师在校对页改过的块一起送上去
    // （以前只传 task_id，后端从 ocr_store 读原始块 → 老师改的公式当场就丢了）
    const res = await createQuestionFromOcr(taskId.value, {
      ...overrides,
      blocks: allBlocks.value,
    })
    message.success(`已入库（第 ${res.data.question.id} 题）`)
    emit('question-saved')
  } catch (e) {
    message.error(`入库失败：${e.response?.data?.detail || e.message}`)
  } finally {
    saving.value = false
  }
}

// === 一键复制(任务 5A:改用 toast 替掉 alert) ===
// alert() 会阻塞页面、样式无法控制、macOS 上像系统弹窗很突兀
// toast 从顶部滑入、自动消失、不打断操作
async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text)
    message.success(`已复制${label}到剪贴板`)
  } catch (e) {
    message.error(`复制失败：${e.message}`)
  }
}

async function copyMarkdown() {
  await copyText(withFormulas.value, ' Markdown')
}

// 复制纯文本（公式用 Unicode: x² 而不是 x^{2}）
async function copyPlainText() {
  await copyText(buildPlainText.value, '纯文本')
}
</script>

<template>
  <NCard title="🔍 OCR 识别结果" size="small">
    <NSpace vertical size="medium">
      <!-- 顶部:状态 + 历史下拉 + 开始按钮 -->
      <NSpace align="center">
        <NTag :type="status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'info'">
          {{ status === 'idle' ? '待识别' : status === 'processing' ? '识别中...' : status === 'completed' ? '已完成' : '失败' }}
        </NTag>
        <NButton type="primary" :disabled="status === 'processing' || !imageUrl" @click="startOcr">
          {{ status === 'completed' ? '🔄 重新识别' : '🚀 开始识别' }}
        </NButton>
        <NSpace v-if="historyOptions.length" align="center">
          <NText depth="3" style="font-size: 12px">历史：</NText>
          <NSelect
            :options="historyOptions"
            :value="taskId"
            placeholder="选一条历史记录"
            size="small"
            style="width: 260px"
            clearable
            @update:value="selectHistory"
          />
        </NSpace>
        <NButton v-if="status === 'completed'" size="small" @click="showEditor = !showEditor">
          {{ showEditor ? '📝 收起编辑器' : '📝 转题目编辑器' }}
        </NButton>
        <NButton
          v-if="status === 'completed'"
          size="small"
          type="primary"
          :loading="saving"
          @click="saveToBank"
        >
          💾 存入题库
        </NButton>
      </NSpace>

      <!-- 错误 -->
      <NAlert v-if="error" type="error" :show-icon="false">❌ {{ error }}</NAlert>

      <!-- Loading -->
      <NSpin v-if="status === 'processing'" size="medium">
        <NEmpty description="PaddleOCR 正在识别(平均 5 秒)..." />
      </NSpin>

      <!-- 任务 4:左右分栏 — 左原图(带 bbox 高亮) · 右结果 -->
      <div v-if="status === 'completed'" style="display: flex; gap: 16px; align-items: flex-start;">
        <!-- 左:原图 + 红框高亮 -->
        <div style="flex: 0 0 45%; min-width: 0;">
          <div style="position: relative; display: inline-block; max-width: 100%; border: 1px solid #d9d9d9; border-radius: 4px; overflow: hidden;">
            <img
              v-if="imageUrl && imageBlobUrl"
              :src="imageBlobUrl"
              alt="原图"
              style="display: block; width: 100%; height: auto;"
              @load="onImageLoad"
            />
            <!-- 高亮框:绝对定位 + 百分比,跟着图片缩放 -->
            <div
              class="ocr-highlight-box"
              :style="highlightStyle"
            />
          </div>
          <NText depth="3" style="font-size: 12px; display: block; margin-top: 4px;">
            原图 {{ imgSize.w }}×{{ imgSize.h }}px · 把鼠标移到右侧内容看对应区域
          </NText>
        </div>

        <!-- 右:识别结果(hover 触发左侧高亮) -->
        <div style="flex: 1; min-width: 0;">
          <!-- 题图：图形从文字流里抽出来单独一张卡，老师一眼就能看到 -->
          <NCard
            v-if="figureBlocks.length"
            size="small"
            title="🖼 题图（从原图裁出，入库时随题保存）"
            style="margin-bottom: 8px;"
          >
            <NSpace>
              <div
                v-for="(fb, fi) in figureBlocks"
                :key="fi"
                class="ocr-figure-card"
              >
                <div :style="figureCropStyle(fb) || {}" />
                <NText depth="3" style="font-size: 11px;">图形 {{ fi + 1 }}</NText>
              </div>
            </NSpace>
          </NCard>

          <NTabs type="line" animated size="small">
            <NTabPane name="text" tab="① 纯文本">
              <OcrBlockList
                :blocks="allBlocks"
                render-mode="simple"
                :hover-index="hoverIndex"
                :figure-image-url="imageBlobUrl"
                :figure-image-size="imgSize"
                :show-figure="false"
                @hover="hoverIndex = $event"
                @update-formula="onFormulaUpdate"
                @update-block="onBlockUpdate"
              />
              <NSpace align="center" justify="space-between" style="margin-top: 6px;">
                <NText depth="3" style="font-size: 12px">
                  共 {{ allBlocks.length }} 个块 · {{ result?.stats?.elapsed_ms }}ms · {{ result?.stats?.model }}
                </NText>
                <NButton size="small" type="primary" @click="copyPlainText">
                  📋 复制纯文本
                </NButton>
              </NSpace>
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
              <OcrBlockList
                :blocks="allBlocks"
                render-mode="rich"
                :hover-index="hoverIndex"
                :figure-image-url="imageBlobUrl"
                :figure-image-size="imgSize"
                :show-figure="false"
                @hover="hoverIndex = $event"
                @update-formula="onFormulaUpdate"
                @update-block="onBlockUpdate"
              />
            </NTabPane>
          </NTabs>
        </div>
      </div>

      <!-- 任务 5:题目编辑器(默认折叠,点顶部按钮展开) -->
      <QuestionEditor
        v-if="showEditor && status === 'completed'"
        :plain-text="plainText"
        :with-formulas="withFormulas"
        :blocks="allBlocks"
        @close="showEditor = false"
        @meta-change="m => (metaOverride = m)"
      />
    </NSpace>
  </NCard>
</template>

<style scoped>
/* 高亮框:红框 + 半透明底 + 指针事件穿透(不然会挡住 hover) */
.ocr-highlight-box {
  position: absolute;
  border: 2px solid #f5222d;
  background: rgba(245, 34, 45, 0.12);
  pointer-events: none;
  transition: all 0.08s ease-out;
  border-radius: 2px;
}
/* 注:block 列表的 hover 样式已搬到 OcrBlockList.vue(父组件 scoped 样式不作用到子组件 DOM) */

/* 题图卡片里的图形 */
.ocr-figure-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}
</style>