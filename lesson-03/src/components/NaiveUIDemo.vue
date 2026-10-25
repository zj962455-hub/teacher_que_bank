<script setup>
import { ref, h, reactive, computed } from 'vue'
import {
  NConfigProvider, NMessageProvider, NDialogProvider,
  darkTheme, zhCN, dateZhCN,
  NButton, NSpace, NSelect, NSwitch, NInput, NTag,
  NCard, NDivider, NDataTable, NForm, NFormItem,
  NInputNumber, NRadioGroup, NRadio, NCheckbox,
  NUpload, NUploadDragger, NIcon, NText, NH1, NH2, NH3,
  NPopconfirm, useMessage, createDiscreteApi, NImage, NEmpty
} from 'naive-ui'

// === 演示数据 ===
const mockQuestions = ref([
  { id: 1, title: '已知 f(x) = x² + 2x + 1,求 f(2)', subject: 'math',    difficulty: 2, type: 'choice',    tags: ['函数', '基础'],     createdAt: '2026-08-20' },
  { id: 2, title: '求 lim(x→0) sin(x)/x 的值',          subject: 'math',    difficulty: 3, type: 'fill',      tags: ['极限'],              createdAt: '2026-08-21' },
  { id: 3, title: '牛顿第二定律的表达式',                subject: 'physics', difficulty: 1, type: 'choice',    tags: ['力学', '基础'],     createdAt: '2026-08-22' },
  { id: 4, title: '计算 ∫₀¹ x² dx',                     subject: 'math',    difficulty: 3, type: 'fill',      tags: ['积分'],              createdAt: '2026-08-23' },
  { id: 5, title: '化学反应中催化剂的作用',              subject: 'chem',    difficulty: 2, type: 'essay',     tags: ['反应原理'],          createdAt: '2026-08-24' },
  { id: 6, title: 'English: "knowledge" 词根',           subject: 'english', difficulty: 1, type: 'choice',    tags: ['词汇'],              createdAt: '2026-08-25' },
  { id: 7, title: '证明:对顶角相等',                     subject: 'math',    difficulty: 2, type: 'proof',     tags: ['几何', '证明'],     createdAt: '2026-08-26' },
])

// === 主题切换 ===
const isDark = ref(false)
const themeReactive = computed(() => (isDark.value ? darkTheme : null))
const themeOverrides = computed(() => ({
  common: {
    primaryColor: '#18a058',
    primaryColorHover: '#36ad6a',
    primaryColorPressed: '#0c7a43',
    primaryColorSuppl: '#36ad6a',
  },
}))

// === 学科 / 难度 / 题型 选项 ===
const subjectOptions = [
  { label: '数学',   value: 'math'    },
  { label: '物理',   value: 'physics' },
  { label: '化学',   value: 'chem'    },
  { label: '英语',   value: 'english' },
]
const difficultyOptions = [
  { label: '★ 简单', value: 1 },
  { label: '★★ 中等', value: 2 },
  { label: '★★★ 困难', value: 3 },
]
const typeOptions = [
  { label: '选择题', value: 'choice' },
  { label: '填空题', value: 'fill'   },
  { label: '解答题', value: 'essay'  },
  { label: '证明题', value: 'proof'  },
]
const subjectMap = Object.fromEntries(subjectOptions.map(o => [o.value, o.label]))
const difficultyMap = Object.fromEntries(difficultyOptions.map(o => [o.value, o.label]))
const typeMap = Object.fromEntries(typeOptions.map(o => [o.value, o.label]))

// === 表格列定义 ===
const columns = computed(() => [
  {
    title: 'ID',
    key: 'id',
    width: 60,
    sorter: (a, b) => a.id - b.id,
  },
  {
    title: '题目',
    key: 'title',
    ellipsis: { tooltip: true },
    resizable: true,
  },
  {
    title: '学科',
    key: 'subject',
    width: 100,
    render(row) {
      return h(NTag, { type: 'success', size: 'small', bordered: false }, () => subjectMap[row.subject])
    },
  },
  {
    title: '难度',
    key: 'difficulty',
    width: 120,
    render(row) {
      const colors = { 1: 'info', 2: 'warning', 3: 'error' }
      return h(NTag, { type: colors[row.difficulty], size: 'small', bordered: false }, () => difficultyMap[row.difficulty])
    },
  },
  {
    title: '题型',
    key: 'type',
    width: 100,
    render(row) { return typeMap[row.type] },
  },
  {
    title: '标签',
    key: 'tags',
    width: 180,
    render(row) {
      return h(NSpace, { size: 4 }, () => row.tags.map(t => h(NTag, { size: 'small', bordered: false }, () => t)))
    },
  },
  {
    title: '日期',
    key: 'createdAt',
    width: 120,
    sorter: (a, b) => a.createdAt.localeCompare(b.createdAt),
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    fixed: 'right',
    render(row) {
      return h(NSpace, { size: 4 }, () => [
        h(NButton, { size: 'small', tertiary: true, onClick: () => viewRow(row) }, () => '查看'),
        h(NPopconfirm, { onPositiveClick: () => deleteRow(row) }, {
          trigger: () => h(NButton, { size: 'small', tertiary: true, type: 'error' }, () => '删除'),
          default: () => `确定删除题目 #${row.id}?`,
        }),
      ])
    },
  },
])

// === 表格筛选 / 分页 ===
const searchKeyword = ref('')
const filterSubject = ref(null)
const filteredData = computed(() => {
  return mockQuestions.value.filter(q => {
    const matchKw = !searchKeyword.value || q.title.includes(searchKeyword.value)
    const matchSubject = !filterSubject.value || q.subject === filterSubject.value
    return matchKw && matchSubject
  })
})
const pagination = reactive({ page: 1, pageSize: 5, showSizePicker: true, pageSizes: [5, 10, 20], onChange: (p) => { pagination.page = p }, onUpdatePageSize: (s) => { pagination.pageSize = s; pagination.page = 1 } })

// === 新增题目表单 ===
const formRef = ref(null)
const formValue = reactive({
  title: '',
  subject: null,
  difficulty: null,
  type: null,
  content: '',
  tags: [],
})
const formRules = {
  title:    { required: true, message: '请输入题目', trigger: ['blur', 'input'] },
  subject:  { required: true, message: '请选学科',   trigger: ['blur', 'change'] },
  difficulty: { required: true, message: '请选难度', trigger: ['blur', 'change'] },
  type:     { required: true, message: '请选题型',   trigger: ['blur', 'change'] },
}
function submitForm() {
  formRef.value?.validate((errors) => {
    if (!errors) {
      const newQ = {
        id: mockQuestions.value.length + 1,
        title: formValue.title,
        subject: formValue.subject,
        difficulty: formValue.difficulty,
        type: formValue.type,
        tags: formValue.tags,
        createdAt: new Date().toISOString().slice(0, 10),
      }
      mockQuestions.value.unshift(newQ)
      message.success(`已新增题目 #${newQ.id}`)
      resetForm()
    } else {
      message.error('表单校验失败,请检查红框字段')
    }
  })
}
function resetForm() {
  Object.assign(formValue, { title: '', subject: null, difficulty: null, type: null, content: '', tags: [] })
}

// === 表格操作 ===
// 用 createDiscreteApi 不依赖 setup 时序（useMessage() 在 setup 里调用时,
// NMessageProvider 还是子组件,还没渲染/没 provide,会报错）
const { message } = createDiscreteApi(['message'])
function viewRow(row)  { message.info(`查看题目 #${row.id}: ${row.title}`) }
function deleteRow(row) { mockQuestions.value = mockQuestions.value.filter(q => q.id !== row.id); message.success(`已删除 #${row.id}`) }

// === 上传(走 lesson-05 后端) ===
const uploadUrl = `${API}/upload/`
</script>

<template>
  <NConfigProvider :theme="themeReactive" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <div class="demo-wrap" :class="{ 'is-dark': isDark }">
          <!-- 顶部工具栏 -->
          <NCard title="🎨 Naive UI Demo · 教培题库前端方案验证" size="small">
            <template #header-extra>
              <NSpace align="center">
                <NText depth="3">暗色模式</NText>
                <NSwitch v-model:value="isDark" size="medium">
                  <template #checked>🌙</template>
                  <template #unchecked>☀️</template>
                </NSwitch>
              </NSpace>
            </template>
            <NSpace>
              <NTag :type="isDark ? 'warning' : 'success'" round>
                {{ isDark ? '当前:Dark Theme' : '当前:Light Theme' }}
              </NTag>
              <NText depth="3">组件库版本:naive-ui · Vue 3 + TS · 按需引入</NText>
            </NSpace>
          </NCard>

          <!-- 一 · 按钮 / 标签 / Switch 演示 -->
          <NCard title="① 基础控件演示" size="small">
            <NSpace vertical size="medium">
              <div>
                <NText strong>Button (5 种 type × 2 种 size)</NText>
              </div>
              <NSpace>
                <NButton>default</NButton>
                <NButton type="primary">primary</NButton>
                <NButton type="info">info</NButton>
                <NButton type="success">success</NButton>
                <NButton type="warning">warning</NButton>
                <NButton type="error">error</NButton>
              </NSpace>
              <NSpace>
                <NButton size="tiny" type="primary">tiny</NButton>
                <NButton size="small" type="primary">small</NButton>
                <NButton size="medium" type="primary">medium</NButton>
                <NButton size="large" type="primary">large</NButton>
              </NSpace>
              <NDivider />
              <NSpace>
                <NTag>默认</NTag>
                <NTag type="success">成功</NTag>
                <NTag type="info">信息</NTag>
                <NTag type="warning">警告</NTag>
                <NTag type="error">错误</NTag>
                <NTag round :bordered="false">圆角无边框</NTag>
              </NSpace>
            </NSpace>
          </NCard>

          <!-- 二 · DataTable 演示 -->
          <NCard title="② 题目列表(DataTable · 搜索 · 筛选 · 分页 · 批量操作)" size="small">
            <NSpace vertical size="medium">
              <NSpace>
                <NInput v-model:value="searchKeyword" placeholder="🔍 搜索题目关键词" clearable style="width: 280px" />
                <NSelect v-model:value="filterSubject" :options="subjectOptions" placeholder="按学科筛选" clearable style="width: 180px" />
                <NText depth="3">命中 {{ filteredData.length }} / {{ mockQuestions.length }} 条</NText>
              </NSpace>

              <NDataTable
                :columns="columns"
                :data="filteredData"
                :pagination="pagination"
                :bordered="false"
                striped
                size="small"
              />
            </NSpace>
          </NCard>

          <!-- 三 · Form 演示 -->
          <NCard title="③ 新增题目表单(Form 校验 · Select · Tag)" size="small">
            <NForm
              ref="formRef"
              :model="formValue"
              :rules="formRules"
              label-placement="left"
              label-width="auto"
              require-mark-placement="right-hanging"
              style="max-width: 600px"
            >
              <NFormItem label="题目" path="title">
                <NInput v-model:value="formValue.title" placeholder="请输入题目内容" />
              </NFormItem>
              <NFormItem label="学科" path="subject">
                <NSelect v-model:value="formValue.subject" :options="subjectOptions" placeholder="选择学科" />
              </NFormItem>
              <NFormItem label="难度" path="difficulty">
                <NRadioGroup v-model:value="formValue.difficulty">
                  <NRadio v-for="o in difficultyOptions" :key="o.value" :value="o.value">{{ o.label }}</NRadio>
                </NRadioGroup>
              </NFormItem>
              <NFormItem label="题型" path="type">
                <NSelect v-model:value="formValue.type" :options="typeOptions" placeholder="选择题型" />
              </NFormItem>
              <NFormItem label="答案/解析">
                <NInput v-model:value="formValue.content" type="textarea" placeholder="选填,题目详细解析或答案" :rows="3" />
              </NFormItem>
              <NFormItem label="标签">
                <NInput v-model:value="formValue.tags" placeholder="(教学笔记里再细化为 tag 输入组件)" />
              </NFormItem>
              <NFormItem>
                <NSpace>
                  <NButton type="primary" @click="submitForm">提交</NButton>
                  <NButton @click="resetForm">重置</NButton>
                </NSpace>
              </NFormItem>
            </NForm>
          </NCard>

          <!-- 四 · Upload 演示(接 lesson-05 后端) -->
          <NCard title="④ 图片上传(接 lesson-05 FastAPI 接口)" size="small">
            <NUpload
              :action="uploadUrl"
              :default-upload="false"
              list-type="image-card"
              multiple
              accept="image/*"
              :max="5"
            >
              <NUploadDragger>
                <NText style="font-size: 32px">📂</NText>
                <NText depth="3" style="display: block; margin-top: 8px">点击或拖拽图片到此处<br>(需后端运行 lesson-02)</NText>
              </NUploadDragger>
            </NUpload>
          </NCard>

          <!-- 五 · Empty / 底部说明 -->
          <NCard size="small">
            <NEmpty description="demo 完。如果觉得 OK,我们就把 naive UI 接入 lesson-06 后续章节" />
          </NCard>
        </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.demo-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  border: 1px dashed #18a058;
  border-radius: 8px;
  margin-top: 24px;
  background: var(--n-color, transparent);
  transition: background 0.3s;
}
.demo-wrap.is-dark {
  border-color: #36ad6a;
}
:deep(.n-card) {
  --n-padding-bottom: 16px;
}
</style>