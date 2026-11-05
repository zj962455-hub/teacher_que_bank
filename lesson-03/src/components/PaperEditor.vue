<script setup>
/**
 * PaperEditor — 组卷页（三栏）— lesson-11
 *
 * 对齐 MVP 原型 ⑦：三栏布局 + 拖拽排序
 *
 *   左 题目筛选 + 题目列表（点 + 加入）
 *   中 试卷区（拖拽排序 / 改题号 / 改分值 / 移除）
 *   右 A4 预览
 *
 * 拖拽用 vuedraggable —— 拖完一次性提交全部 id（后端有批量重排接口）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import {
  NCard, NButton, NSpace, NInput, NSelect, NTag, NText, NEmpty,
  NSpin, NCheckbox, NSkeleton, NDivider, NScrollbar,
} from 'naive-ui'
import draggable from 'vuedraggable'
import { message } from '../composables/discreteApi'
import { renderMathText } from '../utils/mathRenderer'
import {
  listPapers, createPaper, getPaper, updatePaper, deletePaper,
  addPaperQuestion, updatePaperQuestion, removePaperQuestion,
  reorderPaperQuestions, exportPaperPdf,
} from '../api/papers'
import { listQuestions } from '../api/questions'

// === 试卷 ===
const papers = ref([])
const current = ref(null)
const loading = ref(false)
const exporting = ref(false)

// === 左栏：筛选 + 候选题 ===
const filters = ref({
  subject: null,
  question_type: null,
  grade: null,
  difficulty: null,
  keyword: '',
})
const candidates = ref([])
const candidateLoading = ref(false)
const selectedCandidateIds = ref([])

// === 中栏：试卷里的题 ===
const paperItems = ref([])
const dragging = ref(false)

// === 右栏：预览 ===
const previewOpen = ref(true)

const SUBJECT_OPTIONS = ['数学', '物理', '化学', '生物', '未知'].map((v) => ({ label: v, value: v }))
const TYPE_OPTIONS = ['选择题', '填空题', '计算题', '证明题', '应用题', '未知'].map((v) => ({ label: v, value: v }))
const GRADE_OPTIONS = ['初中', '高中', '通用'].map((v) => ({ label: v, value: v }))
const DIFFICULTY_OPTIONS = ['简单', '中等', '困难'].map((v) => ({ label: v, value: v }))

// === 试卷列表 ===
async function loadPapers() {
  loading.value = true
  try {
    const res = await listPapers()
    papers.value = res.data.items || []
  } catch (e) {
    message.error(`加载试卷列表失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function openPaper(paper) {
  try {
    const res = await getPaper(paper.id)
    current.value = res.data
    paperItems.value = res.data.questions || []
  } catch (e) {
    message.error(`打开失败：${e.message}`)
  }
}

async function newPaper() {
  try {
    const res = await createPaper({ title: '未命名试卷', subtitle: '', question_ids: [] })
    message.success('已创建，改下标题吧')
    await loadPapers()
    await openPaper(res.data)
  } catch (e) {
    message.error(`创建失败：${e.message}`)
  }
}

async function removePaper(paper) {
  try {
    await deletePaper(paper.id)
    message.success('已删除')
    if (current.value?.id === paper.id) {
      current.value = null
      paperItems.value = []
    }
    await loadPapers()
  } catch (e) {
    message.error(`删除失败：${e.message}`)
  }
}

async function saveTitle() {
  if (!current.value) return
  try {
    await updatePaper(current.value.id, {
      title: current.value.title,
      subtitle: current.value.subtitle,
    })
    message.success('已保存')
    await loadPapers()
  } catch (e) {
    message.error(`保存失败：${e.message}`)
  }
}

// === 左栏：候选题 ===
async function loadCandidates() {
  candidateLoading.value = true
  try {
    const params = { limit: 100 }
    for (const k of ['subject', 'question_type', 'grade', 'difficulty']) {
      if (filters.value[k]) params[k] = filters.value[k]
    }
    if (filters.value.keyword) params.keyword = filters.value.keyword
    const res = await listQuestions(params)
    candidates.value = res.data.items || []
  } catch (e) {
    message.error(`加载题目失败：${e.message}`)
  } finally {
    candidateLoading.value = false
  }
}

// 已在卷里的题不再出现在候选列表
const inPaperQuestionIds = computed(() => new Set(paperItems.value.map((i) => i.question_id)))
const availableCandidates = computed(() =>
  candidates.value.filter((q) => !inPaperQuestionIds.value.has(q.id)),
)

async function addQuestion(q) {
  if (!current.value) {
    message.warning('先选一张试卷')
    return
  }
  try {
    await addPaperQuestion(current.value.id, { question_id: q.id })
    await openPaper(current.value)
    await loadCandidates()
  } catch (e) {
    message.error(`加入失败：${e.message}`)
  }
}

async function addSelected() {
  if (!selectedCandidateIds.value.length) return
  for (const qid of selectedCandidateIds.value) {
    const q = candidates.value.find((x) => x.id === qid)
    if (q) await addQuestion(q)
  }
  selectedCandidateIds.value = []
}

// === 中栏：改题号/分值/移除 ===
async function changeLabel(item, value) {
  try {
    await updatePaperQuestion(current.value.id, item.id, { label: value })
    item.label = value
  } catch (e) {
    message.error(`修改题号失败：${e.message}`)
  }
}

async function changeScore(item, value) {
  try {
    await updatePaperQuestion(current.value.id, item.id, { score: value })
    item.score = value
  } catch (e) {
    message.error(`修改分值失败：${e.message}`)
  }
}

async function removeItem(item) {
  try {
    await removePaperQuestion(current.value.id, item.id)
    await openPaper(current.value)
    await loadCandidates()
  } catch (e) {
    message.error(`移除失败：${e.message}`)
  }
}

// === 拖拽排序 ===
// vuedraggable 在数组上直接改 —— 这里用 paperItems 承载，拖完提交
async function onDragEnd() {
  if (!current.value) return
  try {
    await reorderPaperQuestions(
      current.value.id,
      paperItems.value.map((i) => i.id),
    )
    message.success('顺序已保存')
    await openPaper(current.value)
  } catch (e) {
    message.error(`保存顺序失败：${e.message}`)
    await openPaper(current.value)   // 回滚到服务端顺序
  }
}

// === 导出 ===
async function exportPdf() {
  if (!paperItems.value.length) {
    message.warning('试卷里还没有题目')
    return
  }
  exporting.value = true
  try {
    const name = await exportPaperPdf(current.value.id, current.value.title)
    message.success(`已导出：${name}`)
  } catch (e) {
    message.error(`导出失败：${e.response?.data?.detail || e.message}`)
  } finally {
    exporting.value = false
  }
}

// === 总分 ===
const totalScore = computed(() =>
  paperItems.value.reduce((sum, i) => sum + (Number(i.score) || 0), 0),
)

onMounted(() => {
  loadPapers()
  loadCandidates()
})
</script>

<template>
  <div class="paper-page">
    <!-- ===== 顶部：试卷选择 ===== -->
    <NCard size="small" style="margin-bottom: 12px">
      <NSpace align="center" wrap>
        <NSelect
          :value="current?.id ?? null"
          :options="papers.map((p) => ({ label: `${p.title} (${p.question_count}题)`, value: p.id }))"
          placeholder="选择试卷"
          size="small"
          style="width: 260px"
          @update:value="(v) => { const p = papers.find((x) => x.id === v); if (p) openPaper(p) }"
        />
        <NButton size="small" @click="newPaper">+ 新建试卷</NButton>
        <NButton v-if="current" size="small" @click="saveTitle">保存标题</NButton>
        <NButton
          v-if="current"
          size="small"
          type="success"
          :loading="exporting"
          :disabled="!paperItems.length"
          @click="exportPdf"
        >
          📄 导出 PDF
        </NButton>
        <NButton
          v-if="current"
          size="small"
          quaternary
          @click="previewOpen = !previewOpen"
        >
          {{ previewOpen ? '隐藏预览' : '显示预览' }}
        </NButton>
        <NText v-if="current" depth="3" style="font-size: 12px; margin-left: auto">
          共 {{ paperItems.length }} 题 · 总分 {{ totalScore }}
        </NText>
      </NSpace>

      <NSpace v-if="current" align="center" style="margin-top: 8px">
        <NText depth="3" style="width: 48px">标题</NText>
        <NInput v-model:value="current.title" size="small" placeholder="试卷标题" style="width: 280px" />
        <NText depth="3" style="width: 60px; margin-left: 8px">副标题</NText>
        <NInput v-model:value="current.subtitle" size="small" placeholder="姓名 / 班级 / 日期" style="width: 240px" />
      </NSpace>
    </NCard>

    <!-- ===== 三栏 ===== -->
    <div class="three-col">
      <!-- 左：选题 -->
      <NCard title="📚 选题" size="small" class="col-left">
        <NSpace vertical size="small">
          <NSpace size="small" wrap>
            <NSelect
              v-model:value="filters.subject"
              :options="SUBJECT_OPTIONS"
              placeholder="学科"
              clearable
              size="tiny"
              style="width: 100px"
              @update:value="loadCandidates"
            />
            <NSelect
              v-model:value="filters.difficulty"
              :options="DIFFICULTY_OPTIONS"
              placeholder="难度"
              clearable
              size="tiny"
              style="width: 100px"
              @update:value="loadCandidates"
            />
            <NSelect
              v-model:value="filters.grade"
              :options="GRADE_OPTIONS"
              placeholder="学段"
              clearable
              size="tiny"
              style="width: 96px"
              @update:value="loadCandidates"
            />
          </NSpace>
          <NSpace size="small">
            <NInput
              v-model:value="filters.keyword"
              placeholder="搜题干"
              size="tiny"
              clearable
              style="width: 190px"
              @keyup.enter="loadCandidates"
            />
            <NButton size="tiny" @click="loadCandidates">搜</NButton>
          </NSpace>

          <NButton
            v-if="selectedCandidateIds.length"
            size="tiny"
            type="primary"
            block
            @click="addSelected"
          >
            加入选中 {{ selectedCandidateIds.length }} 道
          </NButton>
        </NSpace>

        <NSpin :show="candidateLoading">
          <NScrollbar style="max-height: 560px; margin-top: 8px">
            <div
              v-for="q in availableCandidates"
              :key="q.id"
              class="candidate"
              @dblclick="addQuestion(q)"
            >
              <NCheckbox
                :value="q.id"
                @update:checked="(c) => {
                  const set = new Set(selectedCandidateIds)
                  c ? set.add(q.id) : set.delete(q.id)
                  selectedCandidateIds = [...set]
                }"
              />
              <div class="candidate-body">
                <div
                  class="candidate-text"
                  v-html="renderMathText(q.content_markdown || q.content_plain)"
                />
                <NSpace size="small" style="margin-top: 2px">
                  <NTag size="tiny" :bordered="false">{{ q.subject }}</NTag>
                  <NTag size="tiny" :bordered="false" type="warning">{{ q.difficulty }}</NTag>
                </NSpace>
              </div>
              <NButton size="tiny" type="primary" quaternary @click="addQuestion(q)">+</NButton>
            </div>
            <NEmpty
              v-if="!candidateLoading && availableCandidates.length === 0"
              description="没有可加的题目"
              size="small"
              style="padding: 24px 0"
            />
          </NScrollbar>
        </NSpin>
      </NCard>

      <!-- 中：试卷区（拖拽排序） -->
      <NCard title="📝 试卷" size="small" class="col-mid">
        <NEmpty v-if="!current" description="先选一张试卷" style="padding: 32px 0" />
        <NEmpty
          v-else-if="!paperItems.length"
          description="从左边挑题加入"
          style="padding: 32px 0"
        />
        <draggable
          v-else
          v-model="paperItems"
          item-key="id"
          handle=".drag-handle"
          animation="180"
          class="paper-list"
          @end="onDragEnd"
        >
          <template #item="{ element: item, index }">
            <div class="paper-item">
              <span class="drag-handle" title="拖动排序">⠿</span>
              <NInput
                :value="item.label"
                size="tiny"
                placeholder="题号"
                style="width: 62px; flex-shrink: 0"
                @update:value="(v) => changeLabel(item, v)"
              />
              <div
                class="paper-text"
                v-html="renderMathText(item.question.content_markdown || item.question.content_plain)"
              />
              <NInput
                :value="item.score"
                type="number"
                size="tiny"
                placeholder="分"
                style="width: 54px; flex-shrink: 0"
                @update:value="(v) => changeScore(item, Number(v) || 0)"
              />
              <NButton size="tiny" quaternary type="error" @click="removeItem(item)">✕</NButton>
            </div>
          </template>
        </draggable>
      </NCard>

      <!-- 右：预览 -->
      <!-- ⚠️ 常驻渲染(不 v-if current)—— 否则没选卷时整列消失,
      <!--    三栏结构会塌成两栏,布局不稳定 -->
      <NCard v-if="previewOpen" title="👀 预览" size="small" class="col-right">
        <NSpin :show="loading">
          <div v-if="current" class="preview-paper">
            <div class="preview-title">{{ current.title }}</div>
            <div v-if="current.subtitle" class="preview-subtitle">{{ current.subtitle }}</div>
            <NDivider style="margin: 10px 0" />
            <div v-for="item in paperItems" :key="item.id" class="preview-item">
              <span class="preview-label">{{ item.label || '·' }}</span>
              <span
                class="preview-text"
                v-html="renderMathText(item.question.content_markdown || item.question.content_plain)"
              />
              <span v-if="item.score" class="preview-score">{{ item.score }} 分</span>
            </div>
            <NEmpty v-if="!paperItems.length" description="还没有题" size="small" />
          </div>
          <NEmpty v-else description="选一张卷看预览" size="small" style="padding: 32px 0" />
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.three-col {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.col-left {
  width: 330px;
  flex-shrink: 0;
}

.col-mid {
  flex: 1;
  min-width: 0;
}

.col-right {
  width: 320px;
  flex-shrink: 0;
}

/* === 候选题 === */
.candidate {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 4px;
  border-bottom: 1px solid #f5f5f5;
}

.candidate-body {
  flex: 1;
  min-width: 0;
}

.candidate-text {
  font-size: 13px;
  line-height: 1.7;
  max-height: 3.4em;
  overflow: hidden;
}

/* === 试卷区 === */
.paper-list {
  min-height: 120px;
}

.paper-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 4px;
  border-bottom: 1px solid #f0f0f0;
  background: #fff;
}

.drag-handle {
  cursor: grab;
  color: #bbb;
  font-size: 15px;
  line-height: 1.7;
  flex-shrink: 0;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.paper-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}

/* === 预览 === */
.preview-paper {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 16px 14px;
  font-size: 13px;
  line-height: 1.9;
}

.preview-title {
  font-size: 16px;
  font-weight: 600;
  text-align: center;
}

.preview-subtitle {
  font-size: 12px;
  color: #666;
  text-align: center;
}

.preview-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
}

.preview-label {
  flex-shrink: 0;
  font-weight: 600;
}

.preview-text {
  flex: 1;
}

.preview-score {
  flex-shrink: 0;
  color: #999;
  font-size: 12px;
}
</style>
