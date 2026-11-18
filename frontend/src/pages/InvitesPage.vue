<script setup>
/**
 * InvitesPage — 邀请码管理 — lesson-34（灰度试用入口）
 *
 * 谁能进
 * ------
 * 只有管理员（``is_admin``）。前端按 is_admin 显示入口，
 * 后端接口也用 require_admin 挡着 —— 两道门都留着。
 *
 * 干什么
 * ------
 * - 生成一批邀请码（发给老师）
 * - 看着每个码还能用几次、什么时候过期
 * - 一键停用（发错了 / 老师流失了）
 * - 改名额（同一批人多，加几次）
 *
 * 码是明文的
 * ----------
 * 后端明文存、前端明文显示 —— 管理员要能反复复制同一个码发出去。
 * 它不是密码：限次、可停、能过期，只有管理员看得到。
 */
import { ref, onMounted, computed, h } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NInputNumber, NButton, NSpace, NTag,
  NText, NAlert, NEmpty, NDataTable, NPopconfirm,
} from 'naive-ui'
import { listInvites, createInvite, updateInvite } from '../api/invites'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'
import { parseError } from '../utils/errors'
import TaskState from '../components/TaskState.vue'

const items = ref([])

// === 生成表单 ===
const label = ref('')
const maxUses = ref(1)
const expiresDays = ref(30)

const { loading, error, run, retry } = useAsyncTask(async () => {
  const res = await listInvites()
  items.value = res.data.items || []
  return res.data
})

onMounted(() => {
  run().catch(() => undefined)
})

// === 生成 ===
const creating = ref(false)

async function handleCreate() {
  creating.value = true
  try {
    const res = await createInvite({
      label: label.value.trim(),
      max_uses: maxUses.value,
      expires_days: expiresDays.value,
    })
    message.success(`已生成邀请码：${res.data.code}`)
    label.value = ''
    await run().catch(() => undefined)
  } catch (e) {
    message.error(parseError(e).message)
  } finally {
    creating.value = false
  }
}

// === 启停 / 改名额 ===
const busyId = ref(null)

async function toggleActive(item) {
  busyId.value = item.id
  try {
    await updateInvite(item.id, { is_active: !item.is_active })
    message.success(item.is_active ? '已停用' : '已启用')
    await run().catch(() => undefined)
  } catch (e) {
    message.error(parseError(e).message)
  } finally {
    busyId.value = null
  }
}

async function addUse(item) {
  busyId.value = item.id
  try {
    await updateInvite(item.id, { max_uses: item.max_uses + 1 })
    await run().catch(() => undefined)
  } catch (e) {
    message.error(parseError(e).message)
  } finally {
    busyId.value = null
  }
}

async function copyCode(code) {
  try {
    await navigator.clipboard.writeText(code)
    message.success('已复制')
  } catch {
    message.error('复制失败 —— 请手动选中复制')
  }
}

// === 表格列 ===
const columns = computed(() => [
  {
    title: '邀请码',
    key: 'code',
    render: (row) =>
      h(
        NSpace,
        { align: 'center', size: 6 },
        {
          default: () => [
            h('span', { class: 'code-text' }, row.code),
            h(
              NButton,
              { size: 'tiny', quaternary: true, onClick: () => copyCode(row.code) },
              { default: () => '复制' },
            ),
          ],
        },
      ),
  },
  { title: '备注', key: 'label', render: (row) => row.label || '—' },
  {
    title: '名额',
    key: 'max_uses',
    render: (row) => `${row.used_count} / ${row.max_uses}`,
  },
  {
    title: '状态',
    key: 'state',
    render: (row) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: stateType(row.state) },
        { default: () => stateLabel(row.state) },
      ),
  },
  {
    title: '过期时间',
    key: 'expires_at',
    render: (row) => (row.expires_at ? formatTime(row.expires_at) : '永不过期'),
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h(
        NSpace,
        { size: 6 },
        {
          default: () => [
            h(
              NButton,
              {
                size: 'tiny',
                quaternary: true,
                disabled: busyId.value === row.id,
                onClick: () => addUse(row),
              },
              { default: () => '加 1 次' },
            ),
            h(
              NPopconfirm,
              {
                onPositiveClick: () => toggleActive(row),
                positiveText: '确定',
                negativeText: '算了',
              },
              {
                trigger: () =>
                  h(
                    NButton,
                    {
                      size: 'tiny',
                      quaternary: true,
                      type: row.is_active ? 'warning' : 'success',
                      disabled: busyId.value === row.id,
                    },
                    { default: () => (row.is_active ? '停用' : '启用') },
                  ),
                default: () =>
                  row.is_active
                    ? '停用后拿这个码注册的人会被挡在外面，确定？'
                    : '重新启用这个邀请码？',
              },
            ),
          ],
        },
      ),
  },
])

// === 展示用的小工具 ===
function stateType(state) {
  if (state === 'active') return 'success'
  if (state === 'expired') return 'warning'
  return 'default'
}

function stateLabel(state) {
  if (state === 'active') return '可用'
  if (state === 'expired') return '已过期'
  if (state === 'exhausted') return '名额用完'
  return '已停用'
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN')
}
</script>

<template>
  <NCard title="🎟 邀请码管理" :bordered="false">
    <NAlert type="info" :bordered="false" style="margin-bottom: 12px">
      生成邀请码发给老师 —— 他们在登录页切到「注册」页签，填码就能自己注册。
    </NAlert>

    <!-- === 生成 === -->
    <NForm inline style="margin-bottom: 8px" @submit.prevent="handleCreate">
      <NFormItem label="备注">
        <NInput
          v-model:value="label"
          placeholder="给谁发的 / 哪个批次"
          style="width: 220px"
          :disabled="creating"
        />
      </NFormItem>
      <NFormItem label="名额">
        <NInputNumber
          v-model:value="maxUses"
          :min="1"
          :max="100"
          style="width: 110px"
          :disabled="creating"
        />
      </NFormItem>
      <NFormItem label="有效期（天）">
        <NInputNumber
          v-model:value="expiresDays"
          :min="0"
          :max="365"
          style="width: 130px"
          :disabled="creating"
          placeholder="0 = 永不过期"
        />
      </NFormItem>
      <NFormItem>
        <NButton type="primary" :loading="creating" @click="handleCreate">
          生成邀请码
        </NButton>
      </NFormItem>
    </NForm>

    <NText depth="3" style="font-size: 12px; display: block; margin-bottom: 12px">
      有效期填 0 = 永不过期；名额 = 一个码能给几个人用。
    </NText>

    <!-- === 列表 === -->
    <TaskState
      :loading="loading"
      :error="error"
      :empty="!items.length"
      empty-text="还没有邀请码"
      @retry="retry"
    >
      <template #empty>
        <NEmpty description="还没有邀请码 —— 上面生成一个就能发出去了" />
      </template>

      <NDataTable
        :columns="columns"
        :data="items"
        :row-key="(row) => row.id"
        size="small"
      />
    </TaskState>
  </NCard>
</template>

<style scoped>
.code-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  letter-spacing: 0.02em;
}
</style>
