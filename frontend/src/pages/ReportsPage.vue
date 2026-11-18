<script setup>
/**
 * ReportsPage — 举报受理页（仅管理员）— lesson-43
 *
 * 官方第（六）项要「及时发现并处理相关有害信息」——
 * 受理台账 + 一键处置（删题 / 吊销分享 / 停账号）+ 结论回填举报人。
 *
 * 为什么处置动作要「当场执行」而不是只记一笔
 * ------------------------------------------
 * 处置留痕但内容还在，等于没处置。所以这里选动作就真删真停，
 * 执行结果并进处置结论回填给举报人（举报人能凭受理编号查到）。
 *
 * ⚠️ 处置动作**只做一次**：处置过的举报不再重复执行
 *    （重复删题会找不到对象，重复停用会误伤）。这个约束在后端。
 */
import { ref, computed, onMounted, h } from 'vue'
import {
  NCard, NTag, NSpace, NSelect, NText, NEmpty, NSpin, NButton,
  NGrid, NGi, NStatistic, NDivider, NModal, NForm, NFormItem,
  NInput, NAlert, NDataTable,
} from 'naive-ui'
import {
  listReports, getReportSummary, handleReport,
  STATUSES, REASONS, DISPOSE_ACTIONS,
} from '../api/reports'
import { getCachedUser } from '../api/auth'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'
import { parseError } from '../utils/errors'
import TaskState from '../components/TaskState.vue'

const isAdmin = computed(() => !!getCachedUser()?.is_admin)

const items = ref([])
const statusFilter = ref(null)

const statusOptions = [
  { value: null, label: '全部状态' },
  ...STATUSES.map((s) => ({ value: s.value, label: s.label })),
]

const { loading, error, run, retry } = useAsyncTask(async () => {
  const params = {}
  if (statusFilter.value) params.status = statusFilter.value
  const res = await listReports(params)
  items.value = res.data || []
  return res.data
})

// === 汇总统计（仅管理员）===
const summary = ref(null)
const {
  loading: summaryLoading,
  error: summaryError,
  run: loadSummary,
  retry: retrySummary,
} = useAsyncTask(async () => {
  const res = await getReportSummary()
  summary.value = res.data
  return res.data
})

onMounted(() => {
  run().catch(() => undefined)
  if (isAdmin.value) loadSummary().catch(() => undefined)
})

// === 状态筛选 ===
function onFilterChange() {
  run().catch(() => undefined)
}

// === 受理 / 处置弹窗 ===
const showHandle = ref(false)
const current = ref(null)
const handleForm = ref({ status: 'processing', handle_note: '', dispose_action: 'none' })
const handling = ref(false)
const handleError = ref('')

const disposeOptions = DISPOSE_ACTIONS

function openHandle(row) {
  current.value = row
  handleError.value = ''
  handleForm.value = {
    status: row.status === 'pending' ? 'processing' : row.status,
    handle_note: '',
    dispose_action: 'none',
  }
  showHandle.value = true
}

async function doHandle() {
  if (!current.value || handling.value) return
  handling.value = true
  handleError.value = ''
  try {
    const res = await handleReport(current.value.id, handleForm.value)
    message.success('已处置：' + (res.data.handle_note || res.data.status_label))
    showHandle.value = false
    await run()
    await loadSummary()
  } catch (e) {
    handleError.value = parseError(e, '处置失败')
  } finally {
    handling.value = false
  }
}

// === 表格 ===
const statusTagType = {
  pending: 'warning',
  processing: 'info',
  resolved: 'success',
  rejected: 'default',
}

const columns = [
  { title: '受理编号', key: 'report_no', width: 150 },
  { title: '类型', key: 'reason_label', width: 130 },
  { title: '举报对象', key: 'target_desc', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) =>
      h(
        NTag,
        { type: statusTagType[row.status] || 'default', size: 'small', bordered: false },
        { default: () => row.status_label },
      ),
  },
  { title: '举报时间', key: 'created_at', width: 170 },
  {
    title: '操作',
    key: 'ops',
    width: 100,
    render: (row) =>
      h(
        NButton,
        { size: 'small', onClick: () => openHandle(row) },
        { default: () => '受理' },
      ),
  },
]

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
    + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
}
</script>

<template>
  <div class="reports-page">
    <NAlert v-if="!isAdmin" type="warning" :bordered="false">
      举报受理是管理员功能，当前账号没有权限。
    </NAlert>

    <template v-else>
      <!-- 汇总 -->
      <NGrid v-if="summary" :cols="4" :x-gap="12" style="margin-bottom: 16px">
        <NGi>
          <NCard><NStatistic label="举报总数" :value="summary.counts.total" /></NCard>
        </NGi>
        <NGi>
          <NCard><NStatistic label="待受理" :value="summary.counts.pending" /></NCard>
        </NGi>
        <NGi>
          <NCard><NStatistic label="核实中" :value="summary.counts.processing" /></NCard>
        </NGi>
        <NGi>
          <NCard><NStatistic label="已处置" :value="summary.counts.resolved" /></NCard>
        </NGi>
      </NGrid>

      <NCard title="举报受理">
        <NSpace style="margin-bottom: 12px" align="center">
          <NSelect
            v-model:value="statusFilter"
            :options="statusOptions"
            style="width: 160px"
            @update:value="onFilterChange"
          />
          <NButton :loading="loading" @click="run()">刷新</NButton>
          <NText depth="3">处置动作只执行一次，处置过的举报不会重复删改。</NText>
        </NSpace>

        <TaskState
          :loading="loading"
          :error="error"
          @retry="retry"
        >
          <NEmpty v-if="!items.length" description="暂无举报记录" />
          <NDataTable
            v-else
            :columns="columns"
            :data="items"
            :row-key="(row) => row.id"
            :bordered="false"
          />
        </TaskState>
      </NCard>
    </template>

    <!-- 受理 / 处置弹窗 -->
    <NModal
      v-model:show="showHandle"
      preset="card"
      style="max-width: 560px"
      title="受理举报"
    >
      <template v-if="current">
        <NAlert type="info" :bordered="false" style="margin-bottom: 12px">
          <div>受理编号：{{ current.report_no }}</div>
          <div>举报类型：{{ current.reason_label }}</div>
          <div>举报对象：{{ current.target_desc || '（未填写）' }}</div>
          <div>举报说明：{{ current.detail || '（未填写）' }}</div>
          <div>举报人：{{ current.reporter_name || '匿名' }}
            <template v-if="current.reporter_contact">（{{ current.reporter_contact }}）</template>
          </div>
          <div>来源 IP：{{ current.source_ip || '—' }}</div>
        </NAlert>

        <NAlert v-if="handleError" type="error" :bordered="false" style="margin-bottom: 12px">
          {{ handleError }}
        </NAlert>

        <NForm label-placement="top">
          <NFormItem label="处置状态">
            <NSelect v-model:value="handleForm.status" :options="STATUSES" />
          </NFormItem>
          <NFormItem label="处置动作（当场执行，只做一次）">
            <NSelect v-model:value="handleForm.dispose_action" :options="disposeOptions" />
          </NFormItem>
          <NFormItem label="处置结论（回填给举报人）">
            <NInput
              v-model:value="handleForm.handle_note"
              type="textarea"
              :rows="3"
              placeholder="例如：已核实并删除违规题目"
              maxlength="1000"
            />
          </NFormItem>
        </NForm>

        <NSpace justify="end">
          <NButton :disabled="handling" @click="showHandle = false">取消</NButton>
          <NButton type="primary" :loading="handling" @click="doHandle">确认处置</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.reports-page {
  padding: var(--tqb-space-4);
}
</style>
