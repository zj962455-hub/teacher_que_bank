<script setup>
/**
 * QuestionBank — 题库列表 — lesson-08
 *
 * 功能
 * ----
 * - 列表展示（分页）
 * - 多维筛选：学科 / 题型 / 学段 / 难度
 * - 关键词搜索
 * - 删除题目
 * - 空状态 / 加载状态
 */
import { ref, computed, onMounted, h } from 'vue'
import {
  NCard, NDataTable, NButton, NSpace, NSelect, NInput, NTag,
  NEmpty, NSpin, NText, NPopconfirm, NPagination,
} from 'naive-ui'
import { listQuestions, deleteQuestion } from '../api/questions'
import { renderMathText } from '../utils/mathRenderer'
// ⚠️ 用 discreteApi 而不是 useMessage()
//    lesson-07 结论:useMessage() 必须在 <NMessageProvider> 内部,
//    而本项目统一用离散实例(见 src/composables/discreteApi.js)
import { message } from '../composables/discreteApi'

// === 列表数据 ===
const questions = ref([])
const total = ref(0)
const loading = ref(false)

// === 筛选条件 ===
const filters = ref({
  subject: null,
  question_type: null,
  grade: null,
  difficulty: null,
  keyword: '',
})

// === 分页 ===
const page = ref(1)
const pageSize = ref(20)

// === 选项 ===
const SUBJECT_OPTIONS = ['数学', '物理', '化学', '生物', '未知'].map(v => ({ label: v, value: v }))
const TYPE_OPTIONS = ['选择题', '填空题', '计算题', '证明题', '应用题', '未知'].map(v => ({ label: v, value: v }))
const GRADE_OPTIONS = ['初中', '高中', '通用'].map(v => ({ label: v, value: v }))
const DIFFICULTY_OPTIONS = ['简单', '中等', '困难'].map(v => ({ label: v, value: v }))

// === 表格列 ===
const columns = computed(() => [
  {
    title: 'ID',
    key: 'id',
    width: 60,
  },
  {
    title: '题目内容',
    key: 'content_markdown',
    // 用 markdown 版渲染（公式是 $...$，KaTeX 能排版成真正的数学公式）
    // ⚠️ 不用 content_plain：它是 Unicode 版（x²），没有 $ 标记，
    //    renderMathText 认不出来，只会当普通文本显示
    //
    // ⚠️ h() 的 props 用 innerHTML，不是 v-html
    //    v-html 是「模板里的指令语法」，只能写在 <div v-html="..."> 上，
    //    放在 h() 的对象字面量里会直接语法报错。
    render: (row) => h('div', {
      style: 'white-space: pre-wrap; max-height: 80px; overflow: hidden; font-size: 13px;',
      innerHTML: renderMathText(row.content_markdown || row.content_plain),
    }),
  },
  {
    title: '分类',
    key: 'subject',
    width: 220,
    render: (row) => h(NSpace, { size: 4 }, {
      default: () => [
        h(NTag, { size: 'small', bordered: false, type: 'info' }, { default: () => row.subject }),
        h(NTag, { size: 'small', bordered: false, type: 'default' }, { default: () => row.question_type }),
        h(NTag, { size: 'small', bordered: false, type: 'warning' }, { default: () => row.difficulty }),
      ],
    }),
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    render: (row) => h(NSpace, { size: 4, wrap: false }, {
      default: () => [
        h(NButton, {
          size: 'tiny',
          quaternary: true,
          onClick: () => emit('edit', row),
        }, { default: () => '编辑' }),
        h(NPopconfirm, {
          onPositiveClick: () => handleDelete(row),
        }, {
          default: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, { default: () => '删除' }),
          trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, { default: () => '删除' }),
        }),
      ],
    }),
  },
])

// === 加载列表 ===
async function load() {
  loading.value = true
  try {
    const params = {
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    }
    // 只传有值的筛选条件（null 的不传，避免后端收到空字符串）
    for (const key of ['subject', 'question_type', 'grade', 'difficulty']) {
      if (filters.value[key]) params[key] = filters.value[key]
    }
    if (filters.value.keyword) params.keyword = filters.value.keyword

    const res = await listQuestions(params)
    questions.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    message.error(`加载失败：${e.response?.data?.detail || e.message}`)
  } finally {
    loading.value = false
  }
}

// === 筛选变化 → 回到第一页重查 ===
function onFilterChange() {
  page.value = 1
  load()
}

// === 搜索（回车触发）===
function onSearch() {
  page.value = 1
  load()
}

// === 分页 ===
function onPageChange(p) {
  page.value = p
  load()
}

// === 删除 ===
async function handleDelete(row) {
  try {
    await deleteQuestion(row.id)
    message.success('已删除')
    load()
  } catch (e) {
    message.error(`删除失败：${e.response?.data?.detail || e.message}`)
  }
}

// === 暴露给父组件（OCR 卡片入库成功后要刷新列表）===
// ⚠️ <script setup> 的组件默认不暴露内部方法给父组件
//    必须用 defineExpose 显式暴露,否则父组件 ref.value.refresh() 会报
//    "refresh is not a function"
defineExpose({ refresh })

// edit 事件:父组件打开编辑器编辑这道题
const emit = defineEmits(['edit'])

function refresh() {
  page.value = 1
  load()
}

onMounted(load)
</script>

<template>
  <NCard title="📚 我的题库" size="small">
    <NSpace vertical size="medium">
      <!-- 筛选栏 -->
      <NSpace align="center" wrap>
        <NSelect
          v-model:value="filters.subject"
          :options="SUBJECT_OPTIONS"
          placeholder="学科"
          size="small"
          clearable
          style="width: 110px;"
          @update:value="onFilterChange"
        />
        <NSelect
          v-model:value="filters.question_type"
          :options="TYPE_OPTIONS"
          placeholder="题型"
          size="small"
          clearable
          style="width: 110px;"
          @update:value="onFilterChange"
        />
        <NSelect
          v-model:value="filters.grade"
          :options="GRADE_OPTIONS"
          placeholder="学段"
          size="small"
          clearable
          style="width: 100px;"
          @update:value="onFilterChange"
        />
        <NSelect
          v-model:value="filters.difficulty"
          :options="DIFFICULTY_OPTIONS"
          placeholder="难度"
          size="small"
          clearable
          style="width: 100px;"
          @update:value="onFilterChange"
        />
        <NInput
          v-model:value="filters.keyword"
          placeholder="搜索题目内容"
          size="small"
          style="width: 200px;"
          clearable
          @keyup.enter="onSearch"
        />
        <NButton size="small" @click="onSearch">搜索</NButton>
        <NButton size="small" quaternary @click="refresh">刷新</NButton>
        <NText depth="3" style="font-size: 12px; margin-left: auto;">
          共 {{ total }} 题
        </NText>
      </NSpace>

      <!-- 列表 -->
      <NSpin :show="loading">
        <NDataTable
          v-if="questions.length"
          :columns="columns"
          :data="questions"
          :bordered="false"
          :single-line="false"
          size="small"
        />
        <NEmpty v-else description="题库还是空的，去上面 OCR 一道题吧" style="padding: 24px;" />
      </NSpin>

      <!-- 分页 -->
      <div v-if="total > pageSize" style="display: flex; justify-content: center;">
        <NPagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          @update:page="onPageChange"
        />
      </div>
    </NSpace>
  </NCard>
</template>

<style scoped>
/* 让表格里的公式块居中好看一点 */
:deep(.n-data-table-td) {
  vertical-align: top;
}
</style>
