<script setup>
/**
 * QuestionsPage — ③ 题目列表
 *
 * 原型：章节树筛选 + 关键词搜索 + 批量操作
 *
 * 布局
 * ----
 * 左侧章节树（学科 → 学段 → 难度 三层聚合）
 * 右侧：筛选栏 + 搜索 + 表格 + 批量操作条
 *
 * 批量操作
 * --------
 * 表格勾选 → 顶部出现批量条 → 批量改分类/难度 或 批量删除。
 * 后端只处理当前用户的题目，别人的 id 会被跳过。
 */
import { ref, computed, onMounted, h } from 'vue'
import {
  NCard, NButton, NSpace, NInput, NSelect, NTag, NDataTable, NCheckbox,
  NEmpty, NSpin, NPopconfirm, NTree, NAlert, NDivider, useDialog,
} from 'naive-ui'
import { useRouter } from 'vue-router'
import {
  listQuestions, deleteQuestion, exportQuestionsExcel, exportBackupJson,
} from '../api/questions'
import { batchDeleteQuestions, batchUpdateQuestions } from '../api/batch'
import { getCategoryTree, getCategoryFlat, toTreeOptions } from '../api/categories'
import { renderMathText } from '../utils/mathRenderer'
import { message } from '../composables/discreteApi'

const router = useRouter()

// === 数据 ===
const questions = ref([])
const total = ref(0)
const loading = ref(false)
const tree = ref([])
const treeLoading = ref(false)

// === 筛选 ===
const filters = ref({
  subject: null,
  question_type: null,
  grade: null,
  difficulty: null,
  keyword: '',
  // 章节分类（categories.id）—— 后端会把子分类的题也算进来
  category_id: null,
})

/** 扁平分类列表（批量改分类的下拉框用） */
const categoryOptions = ref([])

/** 当前选中的章节（树上的高亮节点） */
const selectedCategory = ref(null)

/** 在 NTree 选项里按 key 找节点名 */
function findOptionLabel(nodes, key) {
  for (const n of nodes) {
    if (n.key === key) return n.label
    if (n.children) {
      const hit = findOptionLabel(n.children, key)
      if (hit) return hit
    }
  }
  return null
}

const page = ref(1)
const pageSize = ref(20)

// === 批量选择 ===
const selectedKeys = ref([])

// === 批量改的表单 ===
const batchForm = ref({
  subject: null,
  question_type: null,
  grade: null,
  difficulty: null,
  category_id: null,
})

const SUBJECT_OPTIONS = ['数学', '物理', '化学', '生物', '未知'].map((v) => ({ label: v, value: v }))
const TYPE_OPTIONS = ['选择题', '填空题', '计算题', '证明题', '应用题', '未知'].map((v) => ({ label: v, value: v }))
const GRADE_OPTIONS = ['初中', '高中', '通用'].map((v) => ({ label: v, value: v }))
const DIFFICULTY_OPTIONS = ['简单', '中等', '困难'].map((v) => ({ label: v, value: v }))

// === 加载 ===
async function load() {
  loading.value = true
  try {
    const params = { ...filters.value, limit: pageSize.value, offset: (page.value - 1) * pageSize.value }
    const res = await listQuestions(params)
    questions.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function loadTree() {
  treeLoading.value = true
  try {
    const [treeRes, flatRes] = await Promise.all([getCategoryTree(), getCategoryFlat()])
    tree.value = toTreeOptions(treeRes.data.tree || [])
    categoryOptions.value = (flatRes.data || []).map((c) => ({ label: c.name, value: c.id }))
  } catch (e) {
    console.error('分类树加载失败:', e.message)
  } finally {
    treeLoading.value = false
  }
}

onMounted(() => {
  load()
  loadTree()
})

// === 筛选变化 ===
function onFilterChange() {
  page.value = 1
  load()
}

function onSearch() {
  page.value = 1
  load()
}

function onPageChange(p) {
  page.value = p
  load()
}

// === 点章节树节点 → 按章节筛选（含子分类） ===
// ⚠️ NTree 的 update:selected-keys 给的是**数组**，不是单个节点
function onTreeSelect(keys) {
  const key = Array.isArray(keys) ? (keys.length ? keys[0] : null) : keys
  filters.value.category_id = key ?? null
  selectedCategory.value = key === null || key === undefined
    ? null
    : { id: key, name: findOptionLabel(tree.value, key) ?? String(key) }
  onFilterChange()
}

/** 清掉章节筛选 */
function clearCategory() {
  filters.value.category_id = null
  selectedCategory.value = null
  onFilterChange()
}

/** 重置所有筛选 */
function resetFilters() {
  filters.value = {
    subject: null, question_type: null, grade: null,
    difficulty: null, keyword: '', category_id: null,
  }
  selectedCategory.value = null
  onFilterChange()
}

// === 批量操作 ===
function clearSelection() {
  selectedKeys.value = []
}

async function doBatchUpdate() {
  const patch = {}
  for (const k of ['subject', 'question_type', 'grade', 'difficulty', 'category_id']) {
    if (batchForm.value[k]) patch[k] = batchForm.value[k]
  }
  if (Object.keys(patch).length === 0) {
    message.warning('先选要改成什么')
    return
  }

  try {
    const res = await batchUpdateQuestions(selectedKeys.value, patch)
    const data = res.data
    message.success(`已改 ${data.updated} 条${data.skipped ? `，跳过 ${data.skipped} 条` : ''}`)
    clearSelection()
    resetBatchForm()
    load()
    loadTree()
  } catch (e) {
    message.error(`批量修改失败：${e.response?.data?.detail || e.message}`)
  }
}

function resetBatchForm() {
  batchForm.value = {
    subject: null, question_type: null, grade: null, difficulty: null, category_id: null,
  }
}

async function doBatchDelete() {
  try {
    const res = await batchDeleteQuestions(selectedKeys.value)
    const data = res.data
    message.success(`已删除 ${data.deleted} 条${data.skipped ? `，跳过 ${data.skipped} 条` : ''}`)
    clearSelection()
    load()
    loadTree()
  } catch (e) {
    message.error(`批量删除失败：${e.response?.data?.detail || e.message}`)
  }
}

async function doDelete(row) {
  try {
    await deleteQuestion(row.id)
    message.success('已删除')
    load()
    loadTree()
  } catch (e) {
    message.error(`删除失败：${e.response?.data?.detail || e.message}`)
  }
}

// === 导出 ===
const exporting = ref(false)

async function doExportExcel() {
  exporting.value = true
  try {
    const name = await exportQuestionsExcel()
    message.success(`已导出：${name}`)
  } catch (e) {
    message.error(`导出失败：${e.response?.data?.detail || e.message}`)
  } finally {
    exporting.value = false
  }
}

async function doExportBackup() {
  exporting.value = true
  try {
    const name = await exportBackupJson()
    message.success(`已备份：${name}`)
  } catch (e) {
    message.error(`备份失败：${e.response?.data?.detail || e.message}`)
  } finally {
    exporting.value = false
  }
}

// === 章节树节点标签 ===
// ⚠️ NTree 的 render-label 收到的是 { option, checked, selected },
//    不是节点本身 —— count 在 option.count 里(TreeOption 是 Record<string, unknown> 扩展)
function renderNodeLabel({ option }) {
  const opt = option || {}
  return `${opt.label ?? ''} (${opt.count ?? 0})`
}

// === 表格 ===
const columns = computed(() => [
  {
    type: 'selection',
    key: 'sel',
  },
  {
    title: 'ID',
    key: 'id',
    width: 60,
  },
  {
    title: '题目内容',
    key: 'content_markdown',
    // ⚠️ h() 的 props 用 innerHTML,不是 v-html
    //    render 直接返回字符串 → NDataTable 当纯文本显示,KaTeX 的 HTML 源码全露出来
    //    (照抄 QuestionBank.vue 的写法)
    render: (row) => h('div', {
      style: 'white-space: pre-wrap; max-height: 80px; overflow: hidden; font-size: 13px;',
      innerHTML: renderMathText(row.content_markdown || row.content_plain),
    }),
  },
  {
    title: '学科',
    key: 'subject',
    width: 80,
    render: (row) => h(NTag, { size: 'small', bordered: false }, { default: () => row.subject }),
  },
  {
    title: '难度',
    key: 'difficulty',
    width: 80,
  },
  {
    title: '操作',
    key: 'ops',
    width: 120,
    render: (row) =>
      h(
        NSpace,
        { size: 4 },
        {
          default: () => [
            h(NButton, { size: 'tiny', onClick: () => router.push({ name: 'question-detail', params: { id: row.id } }) }, { default: () => '详情' }),
            h(
              NPopconfirm,
              { onPositiveClick: () => doDelete(row) },
              {
                trigger: () => h(NButton, { size: 'tiny', type: 'error' }, { default: () => '删除' }),
                default: () => '删除这道题？',
              },
            ),
          ],
        },
      ),
  },
])

// === 表格勾选 ===
const rowKey = (row) => row.id
const checkedRowKeys = computed(() => selectedKeys.value)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">📚 题目列表</h2>
      <NButton type="primary" size="small" @click="router.push({ name: 'capture' })">
        + 录题
      </NButton>
      <NSpace size="small">
        <NButton size="small" @click="doExportExcel">📊 导出 Excel</NButton>
        <NButton size="small" quaternary @click="doExportBackup">💾 备份</NButton>
      </NSpace>
    </div>

    <div class="layout">
      <!-- 左：章节树 -->
      <NCard title="章节" size="small" class="tree-card">
        <NSpin :show="treeLoading">
          <NTree
            v-if="tree.length"
            :data="tree"
            :default-expanded-keys="tree.map((n) => n.key)"
            block-line
            :render-label="renderNodeLabel"
            @update:selected-keys="onTreeSelect"
          />
          <NEmpty v-else description="还没有章节分类" size="small" />
        </NSpin>

        <div v-if="selectedCategory" class="chapter-chip">
          <span class="chip-label">章节</span>
          <span class="chip-name">{{ selectedCategory.name }}</span>
          <NButton size="tiny" quaternary @click="clearCategory">清除</NButton>
        </div>
        <div v-else class="chapter-tip">
          点章节筛选题目（子章节的题也算进来）
        </div>
      </NCard>

      <!-- 右：筛选 + 表格 -->
      <div class="main">
        <NCard size="small">
          <NSpace :size="8" style="flex-wrap: wrap">
            <NSelect
              v-model:value="filters.subject"
              :options="SUBJECT_OPTIONS"
              placeholder="学科"
              clearable
              style="width: 120px"
              @update:value="onFilterChange"
            />
            <NSelect
              v-model:value="filters.question_type"
              :options="TYPE_OPTIONS"
              placeholder="题型"
              clearable
              style="width: 130px"
              @update:value="onFilterChange"
            />
            <NSelect
              v-model:value="filters.grade"
              :options="GRADE_OPTIONS"
              placeholder="学段"
              clearable
              style="width: 110px"
              @update:value="onFilterChange"
            />
            <NSelect
              v-model:value="filters.difficulty"
              :options="DIFFICULTY_OPTIONS"
              placeholder="难度"
              clearable
              style="width: 110px"
              @update:value="onFilterChange"
            />
            <NInput
              v-model:value="filters.keyword"
              placeholder="搜题干关键词"
              clearable
              style="width: 200px"
              @keyup.enter="onSearch"
            />
            <NButton size="small" @click="onSearch">搜索</NButton>
            <NButton size="small" quaternary @click="resetFilters">
              重置
            </NButton>
          </NSpace>
        </NCard>

        <!-- 批量操作条 -->
        <NCard v-if="selectedKeys.length" size="small" style="margin-top: 12px">
          <div class="batch-bar">
            <span class="batch-count">已选 {{ selectedKeys.length }} 条</span>
            <NSpace :size="8" style="flex-wrap: wrap">
              <NSelect
                v-model:value="batchForm.subject"
                :options="SUBJECT_OPTIONS"
                placeholder="改为学科"
                clearable
                style="width: 130px"
              />
              <NSelect
                v-model:value="batchForm.question_type"
                :options="TYPE_OPTIONS"
                placeholder="改为题型"
                clearable
                style="width: 140px"
              />
              <NSelect
                v-model:value="batchForm.grade"
                :options="GRADE_OPTIONS"
                placeholder="改为学段"
                clearable
                style="width: 120px"
              />
              <NSelect
                v-model:value="batchForm.difficulty"
                :options="DIFFICULTY_OPTIONS"
                placeholder="改为难度"
                clearable
                style="width: 120px"
              />
              <NSelect
                v-model:value="batchForm.category_id"
                :options="categoryOptions"
                placeholder="改为章节"
                clearable
                style="width: 150px"
              />
              <NButton size="small" type="primary" @click="doBatchUpdate">批量修改</NButton>
              <NButton size="small" type="error" @click="doBatchDelete">批量删除</NButton>
              <NButton size="small" quaternary @click="clearSelection">取消选择</NButton>
            </NSpace>
          </div>
        </NCard>

        <NCard size="small" style="margin-top: 12px">
          <NSpin :show="loading">
            <NDataTable
              :columns="columns"
              :data="questions"
              :row-key="rowKey"
              v-model:checked-row-keys="selectedKeys"
              :pagination="{
                page: page,
                pageSize: pageSize,
                itemCount: total,
                showSizePicker: true,
                pageSizes: [20, 50, 100],
              }"
              :remote="true"
              size="small"
              @update:page="onPageChange"
              @update:page-size="(s) => { pageSize = s; page = 1; load() }"
            >
              <template #empty>
                <NEmpty description="没有符合条件的题目" />
              </template>
            </NDataTable>
          </NSpin>
        </NCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  font-size: 18px;
}

.layout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.tree-card {
  width: 260px;
  flex-shrink: 0;
}

.main {
  flex: 1;
  min-width: 0;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.batch-count {
  font-size: 13px;
  font-weight: 600;
}

.chapter-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #f2f6fb;
  font-size: 12px;
}

.chip-label {
  color: #888;
}

.chip-name {
  font-weight: 600;
}

.chapter-tip {
  margin-top: 10px;
  color: #999;
  font-size: 12px;
  line-height: 1.5;
}
</style>
