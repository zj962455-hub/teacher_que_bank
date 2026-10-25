<script setup>
/**
 * PaperEditor — 组卷界面 — lesson-09
 *
 * 功能
 * ----
 * - 试卷列表（新建/打开/删除）
 * - 标题/副标题编辑（老师自定义）
 * - 选题（从题库里挑）
 * - 调顺序、改题号、改分值
 * - 导出 PDF
 */
import { ref, computed, onMounted } from 'vue'
import {
  NCard, NButton, NSpace, NInput, NSelect, NTag, NText, NEmpty,
  NSpin, NModal, NList, NListItem, NPopconfirm,
} from 'naive-ui'
// ⚠️ 用 discreteApi 而不是 useMessage()
//    lesson-07 结论:useMessage() 必须在 <NMessageProvider> 内部,
//    本项目统一用离散实例(见 src/composables/discreteApi.js)
import { message } from '../composables/discreteApi'
import { renderMathText } from '../utils/mathRenderer'
import {
  listPapers, createPaper, getPaper, updatePaper, deletePaper,
  addPaperQuestion, updatePaperQuestion, removePaperQuestion, exportPaperPdf,
} from '../api/papers'
import { listQuestions } from '../api/questions'

// === 状态 ===
const papers = ref([])
const current = ref(null)          // 当前试卷详情
const loading = ref(false)
const exporting = ref(false)

// 选题弹窗
const showPicker = ref(false)
const pickerKeyword = ref('')
const pickerSubject = ref(null)
const candidateQuestions = ref([])
const pickerLoading = ref(false)

// === 试卷列表 ===
async function loadPapers() {
  loading.value = true
  try {
    const res = await listPapers()
    papers.value = res.data.items
  } catch (e) {
    message.error(`加载试卷列表失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

// === 打开试卷 ===
async function openPaper(paper) {
  try {
    const res = await getPaper(paper.id)
    current.value = res.data
  } catch (e) {
    message.error(`打开失败：${e.message}`)
  }
}

// === 新建试卷 ===
async function newPaper() {
  try {
    const res = await createPaper({ title: '未命名试卷', subtitle: '', question_ids: [] })
    message.success('已创建，去改标题吧')
    await loadPapers()
    current.value = res.data
  } catch (e) {
    message.error(`创建失败：${e.message}`)
  }
}

// === 删除试卷 ===
async function removePaper(paper) {
  try {
    await deletePaper(paper.id)
    message.success('已删除')
    if (current.value?.id === paper.id) current.value = null
    await loadPapers()
  } catch (e) {
    message.error(`删除失败：${e.message}`)
  }
}

// === 保存标题/副标题 ===
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

// === 打开选题弹窗 ===
async function openPicker() {
  showPicker.value = true
  await loadCandidates()
}

async function loadCandidates() {
  pickerLoading.value = true
  try {
    const params = { limit: 100 }
    if (pickerSubject.value) params.subject = pickerSubject.value
    if (pickerKeyword.value) params.keyword = pickerKeyword.value
    const res = await listQuestions(params)
    candidateQuestions.value = res.data.items
  } catch (e) {
    message.error(`加载题目失败：${e.message}`)
  } finally {
    pickerLoading.value = false
  }
}

// === 加题 ===
async function addQuestion(q) {
  try {
    await addPaperQuestion(current.value.id, { question_id: q.id })
    message.success('已加入')
    await openPaper(current.value)
    await loadCandidates()
  } catch (e) {
    message.error(`加入失败：${e.message}`)
  }
}

// === 移除题 ===
async function removeItem(item) {
  try {
    await removePaperQuestion(current.value.id, item.id)
    await openPaper(current.value)
  } catch (e) {
    message.error(`移除失败：${e.message}`)
  }
}

// === 改题号 ===
async function changeLabel(item, value) {
  try {
    await updatePaperQuestion(current.value.id, item.id, { label: value })
    item.label = value
  } catch (e) {
    message.error(`修改题号失败：${e.message}`)
  }
}

// === 改分值 ===
async function changeScore(item, value) {
  try {
    await updatePaperQuestion(current.value.id, item.id, { score: value })
    item.score = value
  } catch (e) {
    message.error(`修改分值失败：${e.message}`)
  }
}

// === 上移/下移 ===
async function moveItem(index, delta) {
  const items = current.value.questions
  const target = index + delta
  if (target < 0 || target >= items.length) return

  const tmp = items[index]
  items[index] = items[target]
  items[target] = tmp

  // 逐个更新 order_index
  try {
    for (let i = 0; i < items.length; i++) {
      await updatePaperQuestion(current.value.id, items[i].id, { order_index: i })
    }
    // 题号留空时自动重排
    await openPaper(current.value)
  } catch (e) {
    message.error(`调整顺序失败：${e.message}`)
    await openPaper(current.value)
  }
}

// === 导出 PDF ===
async function exportPdf() {
  if (!current.value?.questions?.length) {
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

onMounted(loadPapers)
</script>

<template>
  <NCard title="📝 组卷" size="small">
    <NSpace vertical size="medium">
      <!-- ===== 试卷列表 ===== -->
      <NSpace align="center">
        <NText depth="3">我的试卷：</NText>
        <NSelect
          :value="current?.id ?? null"
          :options="papers.map(p => ({ label: `${p.title} (${p.question_count}题)`, value: p.id }))"
          placeholder="选择试卷"
          size="small"
          style="width: 260px;"
          @update:value="(v) => papers.find(p => p.id === v) && openPaper(papers.find(p => p.id === v))"
        />
        <NButton size="small" @click="newPaper">+ 新建试卷</NButton>
        <NButton size="small" quaternary @click="loadPapers">刷新</NButton>
      </NSpace>

      <!-- ===== 试卷详情 ===== -->
      <div v-if="current">
        <!-- 标题编辑 -->
        <NSpace vertical size="small" style="margin-bottom: 12px;">
          <NSpace align="center">
            <NText depth="3" style="width: 48px;">标题</NText>
            <NInput v-model:value="current.title" size="small" placeholder="试卷标题" style="width: 300px;" />
          </NSpace>
          <NSpace align="center">
            <NText depth="3" style="width: 48px;">副标题</NText>
            <NInput v-model:value="current.subtitle" size="small" placeholder="姓名 / 班级 / 日期（可选）" style="width: 300px;" />
          </NSpace>
        </NSpace>

        <!-- 工具栏 -->
        <NSpace align="center" style="margin-bottom: 10px;">
          <NButton size="small" type="primary" @click="saveTitle">保存标题</NButton>
          <NButton size="small" @click="openPicker">➕ 选题</NButton>
          <NButton size="small" type="success" :loading="exporting" @click="exportPdf">
            📄 导出 PDF
          </NButton>
          <NText depth="3" style="font-size: 12px; margin-left: auto;">
            共 {{ current.questions.length }} 题
          </NText>
        </NSpace>

        <!-- 题目列表 -->
        <div v-if="current.questions.length" style="border: 1px solid #e8e8e8; border-radius: 4px; padding: 8px;">
          <div
            v-for="(item, index) in current.questions"
            :key="item.id"
            style="display: flex; align-items: flex-start; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f0f0f0;"
          >
            <!-- 题号（可改） -->
            <NInput
              :value="item.label"
              size="tiny"
              style="width: 68px; flex-shrink: 0;"
              @update:value="(v) => changeLabel(item, v)"
            />

            <!-- 题目内容 -->
            <div
              style="flex: 1; min-width: 0; font-size: 13px; white-space: pre-wrap; line-height: 1.8;"
              v-html="renderMathText(item.question.content_markdown || item.question.content_plain)"
            />

            <!-- 分值 -->
            <NInput
              :value="item.score"
              type="number"
              size="tiny"
              placeholder="分"
              style="width: 60px; flex-shrink: 0;"
              @update:value="(v) => changeScore(item, Number(v) || 0)"
            />

            <!-- 顺序 / 删除 -->
            <NSpace size="small" :wrap="false">
              <NButton size="tiny" quaternary :disabled="index === 0" @click="moveItem(index, -1)">↑</NButton>
              <NButton size="tiny" quaternary :disabled="index === current.questions.length - 1" @click="moveItem(index, 1)">↓</NButton>
              <NPopconfirm @positive-click="removeItem(item)">
                <template #trigger>
                  <NButton size="tiny" quaternary type="error">✕</NButton>
                </template>
                从试卷中移除这道题？
              </NPopconfirm>
            </NSpace>
          </div>
        </div>

        <NEmpty v-else description="这张试卷还没有题，点「➕ 选题」" style="padding: 24px;" />
      </div>

      <NEmpty v-else description="选一张试卷，或新建一张" style="padding: 24px;" />
    </NSpace>

    <!-- ===== 选题弹窗 ===== -->
    <NModal v-model:show="showPicker" title="从题库选题" style="width: 720px;">
      <NSpace vertical size="medium">
        <NSpace align="center">
          <NInput
            v-model:value="pickerKeyword"
            placeholder="搜索题目内容"
            size="small"
            style="width: 260px;"
            @keyup.enter="loadCandidates"
          />
          <NSelect
            v-model:value="pickerSubject"
            :options="['数学','物理','化学','生物'].map(s => ({label:s, value:s}))"
            placeholder="学科"
            size="small"
            clearable
            style="width: 120px;"
            @update:value="loadCandidates"
          />
          <NButton size="small" @click="loadCandidates">搜索</NButton>
        </NSpace>

        <NSpin :show="pickerLoading">
          <NList v-if="candidateQuestions.length" hoverable>
            <NListItem v-for="q in candidateQuestions" :key="q.id">
              <NSpace align="center" justify="space-between">
                <div
                  style="flex: 1; min-width: 0; font-size: 13px; white-space: pre-wrap;"
                  v-html="renderMathText(q.content_markdown || q.content_plain)"
                />
                <NSpace size="small" :wrap="false">
                  <NTag size="small" :bordered="false">{{ q.subject }}</NTag>
                  <NTag size="small" :bordered="false" type="warning">{{ q.difficulty }}</NTag>
                  <NButton size="tiny" type="primary" @click="addQuestion(q)">加入</NButton>
                </NSpace>
              </NSpace>
            </NListItem>
          </NList>
          <NEmpty v-else-if="!pickerLoading" description="没有匹配的题目" style="padding: 24px;" />
        </NSpin>
      </NSpace>
    </NModal>
  </NCard>
</template>
