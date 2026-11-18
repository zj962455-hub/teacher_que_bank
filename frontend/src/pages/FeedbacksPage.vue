<script setup>
/**
 * FeedbacksPage — 反馈记录页 — lesson-34
 *
 * 谁能看什么
 * ----------
 * - 普通用户：只看到自己提的反馈（后端就这么给的，不是前端过滤的）
 * - 管理员：看到全部，且多一列「谁提的」；还能改处理状态
 *
 * 状态三态：待处理(new) → 已读(read) → 已处理(resolved)
 *
 * 管理员额外能拿「反馈结果」
 * ----------------------
 * 顶部统计卡片（总数 / 待处理 / 已处理 / 三个类别分布）+ 提交人分布 +
 * 两个导出按钮（Markdown / CSV）—— 老大要能直接转发或存档。
 *
 * ⚠️ 共享账号下 user_id 全一样 —— 「谁提的」靠 reporter 区分，
 *    所以管理员视图里 reporter / contact 一定要显眼。
 *
 * 异步状态走 useAsyncTask + TaskState（课 32）：
 * 出错显示后端的人话 + 「重试」按钮，不是一片空白。
 */
import { ref, computed, onMounted } from 'vue'
import {
  NCard, NTag, NSpace, NSelect, NText, NEmpty, NSpin, NButton,
  NGrid, NGi, NStatistic, NDivider,
} from 'naive-ui'
import {
  listFeedbacks, updateFeedbackStatus, getFeedbackSummary, exportFeedbacks, STATUSES,
} from '../api/feedback'
import { getCachedUser } from '../api/auth'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'
import { parseError } from '../utils/errors'
import TaskState from '../components/TaskState.vue'

const items = ref([])

// 管理员？—— /auth/me 返回的 is_admin（前端据此显示入口，后端也会再挡一次）
const isAdmin = computed(() => !!getCachedUser()?.is_admin)

const { loading, error, run, retry } = useAsyncTask(async () => {
  const res = await listFeedbacks()
  items.value = res.data.items || []
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
  const res = await getFeedbackSummary()
  summary.value = res.data
  return res.data
})

onMounted(() => {
  run().catch(() => undefined)
  // 汇总接口仅管理员能调 —— 普通用户调会 403，不去打扰后端
  if (isAdmin.value) loadSummary().catch(() => undefined)
})

// === 改状态（仅管理员）===
const updatingId = ref(null)

async function changeStatus(item, status) {
  if (!status || status === item.status) return
  updatingId.value = item.id
  try {
    await updateFeedbackStatus(item.id, status)
    message.success('状态已更新')
    await run().catch(() => undefined)
    await loadSummary().catch(() => undefined)
  } catch (e) {
    message.error(parseError(e).message)
  } finally {
    updatingId.value = null
  }
}

// === 导出（仅管理员）===
const exporting = ref('')

/**
 * 导出接口返回的是 blob —— 错误体也是 blob（JSON），得自己读出来
 * 不然 parseError 只能给一句「服务器返回了未预期的错误」。
 */
async function readBlobError(e) {
  const data = e.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      if (parsed && parsed.detail) return String(parsed.detail)
    } catch {
      // 不是 JSON —— 走下面的兜底
    }
  }
  return parseError(e).message
}

async function handleExport(format) {
  exporting.value = format
  try {
    const res = await exportFeedbacks(format)
    const isCsv = format === 'csv'
    const blob = new Blob([res.data], {
      type: isCsv ? 'text/csv;charset=utf-8' : 'text/markdown;charset=utf-8',
    })
    const url = window.URL.createObjectURL(blob)
    const stamp = new Date().toISOString().slice(0, 10)
    const a = document.createElement('a')
    a.href = url
    a.download = `feedbacks-${stamp}.${isCsv ? 'csv' : 'md'}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    message.success(`已导出 ${isCsv ? 'CSV' : 'Markdown'}`)
  } catch (e) {
    message.error(await readBlobError(e))
  } finally {
    exporting.value = ''
  }
}

// === 展示用的小工具 ===
function statusType(status) {
  if (status === 'resolved') return 'success'
  if (status === 'read') return 'info'
  return 'warning'
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN')
}
</script>

<template>
  <NCard title="💬 反馈记录" :bordered="false">
    <NText depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
      <template v-if="isAdmin">
        管理员视角：所有人的反馈都在这儿，处理完把状态改成「已处理」。
      </template>
      <template v-else>
        这里是你提过的反馈。处理后状态会变成「已处理」。
      </template>
    </NText>

    <!-- === 管理员：统计卡片 + 导出 === -->
    <template v-if="isAdmin">
      <TaskState
        :loading="summaryLoading"
        :error="summaryError"
        @retry="retrySummary"
      >
        <NGrid :cols="3" :x-gap="12">
          <NGi><NStatistic label="反馈总数" :value="summary?.total ?? 0" /></NGi>
          <NGi><NStatistic label="待处理" :value="summary?.new_count ?? 0" /></NGi>
          <NGi><NStatistic label="已处理" :value="summary?.resolved_count ?? 0" /></NGi>
        </NGrid>

        <NGrid :cols="3" :x-gap="12" style="margin-top: 12px">
          <NGi><NStatistic label="功能异常" :value="summary?.by_category?.bug ?? 0" /></NGi>
          <NGi><NStatistic label="功能建议" :value="summary?.by_category?.feature ?? 0" /></NGi>
          <NGi><NStatistic label="其它" :value="summary?.by_category?.other ?? 0" /></NGi>
        </NGrid>

        <!-- 提交人分布（共享账号下靠它区分老师） -->
        <template v-if="summary?.contributors?.length">
          <NDivider style="margin: 14px 0 10px" />
          <NText depth="3" style="font-size: 12px">谁提的：</NText>
          <NSpace style="margin-top: 6px">
            <NTag
              v-for="c in summary.contributors"
              :key="c.reporter || c.username"
              size="small"
              type="info"
              :bordered="false"
            >
              {{ c.reporter || c.display_name || c.username }} · {{ c.count }} 条
            </NTag>
          </NSpace>
        </template>
      </TaskState>

      <NSpace style="margin-top: 14px">
        <NButton
          size="small"
          :loading="exporting === 'markdown'"
          :disabled="!!exporting"
          @click="handleExport('markdown')"
        >
          📄 导出 Markdown
        </NButton>
        <NButton
          size="small"
          :loading="exporting === 'csv'"
          :disabled="!!exporting"
          @click="handleExport('csv')"
        >
          📊 导出 CSV
        </NButton>
        <NText depth="3" style="font-size: 12px">
          导出内容含提交人、联系方式、状态和来源页面。
        </NText>
      </NSpace>

      <NDivider />
    </template>

    <TaskState
      :loading="loading"
      :error="error"
      :empty="!items.length"
      empty-text="还没有反馈记录"
      @retry="retry"
    >
      <template #empty>
        <NEmpty description="还没有反馈记录 —— 遇到问题点顶栏的「反馈」说一声">
          <template #extra>
            <NText depth="3" style="font-size: 12px">
              提了也没关系，提了才会有人改。
            </NText>
          </template>
        </NEmpty>
      </template>

      <NSpace vertical :size="10">
        <NCard v-for="item in items" :key="item.id" size="small" :bordered="true">
          <div class="fb-head">
            <NSpace :size="8" align="center">
              <NTag size="small" :bordered="false">{{ item.category_label }}</NTag>
              <NTag size="small" :type="statusType(item.status)" :bordered="false">
                {{ item.status_label }}
              </NTag>
              <!-- 管理员才看得到是谁提的 -->
              <NTag v-if="isAdmin && item.username" size="small" type="info" :bordered="false">
                {{ item.display_name || item.username }}
                <template v-if="item.display_name">（{{ item.username }}）</template>
              </NTag>
            </NSpace>
            <NText depth="3" style="font-size: 12px">
              {{ formatTime(item.created_at) }}
            </NText>
          </div>

          <!-- 谁提的 / 联系方式（共享账号下靠这个区分老师） -->
          <div v-if="isAdmin" class="fb-reporter">
            <NText depth="3" style="font-size: 12px">
              提交人：{{ item.reporter || '（未署名）' }}
              <template v-if="item.username">· 账号 {{ item.username }}</template>
              · 联系方式：{{ item.contact || '（未留）' }}
            </NText>
          </div>

          <div class="fb-content">{{ item.content }}</div>

          <NText v-if="item.page_url" depth="3" style="font-size: 12px">
            页面：{{ item.page_url }}
          </NText>

          <!-- 管理员：改处理状态 -->
          <div v-if="isAdmin" class="fb-actions">
            <NSelect
              :value="item.status"
              :options="STATUSES"
              size="small"
              style="max-width: 160px"
              :disabled="updatingId === item.id"
              @update:value="(v) => changeStatus(item, v)"
            />
            <NSpin v-if="updatingId === item.id" size="small" />
          </div>
        </NCard>
      </NSpace>
    </TaskState>
  </NCard>
</template>

<style scoped>
.fb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.fb-reporter {
  margin-top: 6px;
}

.fb-content {
  font-size: 14px;
  line-height: 1.7;
  margin: 8px 0 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

.fb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
</style>
