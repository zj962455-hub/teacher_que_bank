<script setup>
/**
 * ProfilePanel — 个人中心 — lesson-11
 *
 * 功能
 * ----
 * - 账号信息（用户名/显示名/最后登录时间）
 * - 修改显示名
 * - 我的数据统计（题目/试卷/上传数 + 按学科分组）
 * - 修改密码（改完会被踢下线，需重新登录）
 *   ⚠️ 共享试用账号（allow_password_change=false）不显示改密表单 ——
 *      改密会踢掉**所有**共用这个账号的老师的会话。
 *      **前端只是提示，真正的门在后端**（改密接口自己 403）。
 * - 我的登录会话（看有几台设备登着，可单独踢掉）
 * - 退出登录
 *
 * 为什么用「面板」而不是独立路由
 * -----------------------------
 * 单页应用，切面板不用跳路由、不丢当前页面状态。
 */
import { ref, computed, onMounted, h } from 'vue'
import {
  NCard, NButton, NSpace, NInput, NForm, NFormItem, NTag, NStatistic,
  NDivider, NAlert, NSpin, NDataTable, NEmpty, NPopconfirm, NText,
  NDescriptions, NDescriptionsItem, NGrid, NGi,
} from 'naive-ui'
import { message } from '../composables/discreteApi'
import { logout, changePassword } from '../api/auth'
import {
  getMe, updateProfile, getMyStats, listMySessions, revokeSession,
} from '../api/profile'

const props = defineProps({
  user: { type: Object, default: null },
})
const emit = defineEmits(['logged-out', 'profile-updated'])

const loading = ref(true)
const saving = ref(false)
const changingPwd = ref(false)

const me = ref(null)
const stats = ref(null)
const sessions = ref([])

// === 修改显示名 ===
const displayName = ref('')

// === 修改密码 ===
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

// 共享试用账号？—— 改密会把其他老师一起踢下线，直接藏掉改密表单
const pwdLocked = computed(() => me.value?.allow_password_change === false)

// 后端给的人话文案（前端同款，避免两边说法不一致）
const PWD_LOCKED_TEXT =
  '该账号是共享试用账号，改密码会把其他老师一起踢下线，需要改请联系管理员。'

// === 改密前的强度提示 ===
const pwdChecks = computed(() => {
  const p = newPassword.value
  if (!p) return []
  const list = []
  if (p.length < 8) list.push('至少 8 位')
  if (!/[a-z]/.test(p)) list.push('需要小写字母')
  if (!/[A-Z]/.test(p)) list.push('需要大写字母')
  if (!/\d/.test(p)) list.push('需要数字')
  return list
})

const pwdOk = computed(() => newPassword.value && pwdChecks.value.length === 0)

async function load() {
  loading.value = true
  try {
    const [meRes, statsRes, sessRes] = await Promise.all([
      getMe(),
      getMyStats(),
      listMySessions(),
    ])
    me.value = meRes.data
    displayName.value = me.value.display_name || ''
    stats.value = statsRes.data
    sessions.value = sessRes.data
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// === 保存显示名 ===
async function saveProfile() {
  saving.value = true
  try {
    const res = await updateProfile({ display_name: displayName.value })
    me.value = res.data
    emit('profile-updated', res.data)
    message.success('已保存')
  } catch (e) {
    message.error(`保存失败：${e.response?.data?.detail || e.message}`)
  } finally {
    saving.value = false
  }
}

// === 修改密码 ===
async function doChangePassword() {
  if (!pwdOk.value) {
    message.error('新密码不符合强度要求')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    message.error('两次输入的新密码不一致')
    return
  }

  changingPwd.value = true
  try {
    await changePassword(oldPassword.value, newPassword.value)
    message.success('密码已修改，请重新登录')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    // 后端改密后会话全被踢掉 → 直接回登录态
    emit('logged-out')
  } catch (e) {
    message.error(e.response?.data?.detail || `修改失败：${e.message}`)
  } finally {
    changingPwd.value = false
  }
}

// === 踢掉某个会话 ===
async function doRevoke(row) {
  try {
    await revokeSession(row.id)
    sessions.value = sessions.value.filter((s) => s.id !== row.id)
    message.success('已注销该会话')
  } catch (e) {
    message.error(`注销失败：${e.message}`)
  }
}

// === 退出登录 ===
async function doLogout() {
  try {
    await logout()
  } catch {
    // 后端失败也要清本地 —— 本地清理不能依赖网络
  }
  emit('logged-out')
}

// === 会话表格 ===
const sessionColumns = computed(() => [
  { title: 'IP', key: 'ip', width: 130 },
  { title: '最近使用', key: 'last_used_at', width: 180 },
  {
    title: '状态',
    key: 'expired',
    width: 90,
    render: (row) =>
      h(NTag, { type: row.expired ? 'default' : 'success', size: 'small' },
        { default: () => (row.expired ? '已过期' : '有效') }),
  },
  {
    title: '',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NPopconfirm,
        { onPositiveClick: () => doRevoke(row) },
        {
          trigger: () => h(NButton, { size: 'tiny', type: 'error' }, { default: () => '注销' }),
          default: () => '注销这个会话？',
        },
      ),
  },
])

// === 设备 UA 友好化 ===
function shortUa(ua) {
  if (!ua) return '未知设备'
  if (/iPhone|iPad/.test(ua)) return 'iOS 设备'
  if (/Android/.test(ua)) return 'Android 设备'
  if (/Windows/.test(ua)) return 'Windows 电脑'
  if (/Macintosh|Mac OS X/.test(ua)) return 'Mac 电脑'
  if (/Chrome/.test(ua)) return 'Chrome 浏览器'
  return ua.slice(0, 40)
}
</script>

<template>
  <NCard title="👤 个人中心" style="max-width: 760px" :bordered="false">
    <NSpin :show="loading">
      <template v-if="me">
        <!-- === 账号信息 === -->
        <NDescriptions :column="2" label-placement="left" size="small">
          <NDescriptionsItem label="用户名">
            <NTag size="small">{{ me.username }}</NTag>
          </NDescriptionsItem>
          <NDescriptionsItem label="显示名">{{ me.display_name || '（未设置）' }}</NDescriptionsItem>
          <NDescriptionsItem label="最后登录">
            {{ me.last_login_at ? new Date(me.last_login_at).toLocaleString('zh-CN') : '—' }}
          </NDescriptionsItem>
          <NDescriptionsItem label="账号状态">
            <NTag type="success" size="small">正常</NTag>
          </NDescriptionsItem>
        </NDescriptions>

        <NDivider />

        <!-- === 我的数据统计 === -->
        <NGrid :cols="3" :x-gap="12">
          <NGi><NStatistic label="题目" :value="stats?.questions ?? 0" /></NGi>
          <NGi><NStatistic label="试卷" :value="stats?.papers ?? 0" /></NGi>
          <NGi><NStatistic label="上传图片" :value="stats?.uploads ?? 0" /></NGi>
        </NGrid>

        <div v-if="stats?.by_subject?.length" style="margin-top: 12px">
          <NText depth="3" style="font-size: 12px">按学科：</NText>
          <NSpace style="margin-top: 6px">
            <NTag
              v-for="s in stats.by_subject"
              :key="s.subject"
              size="small"
              :bordered="false"
            >
              {{ s.subject }} {{ s.count }}
            </NTag>
          </NSpace>
        </div>

        <NDivider />

        <!-- === 修改显示名 === -->
        <NForm>
          <NFormItem label="显示名">
            <NSpace style="width: 100%">
              <NInput
                v-model:value="displayName"
                placeholder="给同事看名字（最多 50 字）"
                :maxlength="50"
                style="max-width: 320px"
              />
              <NButton type="primary" :loading="saving" @click="saveProfile">
                保存
              </NButton>
            </NSpace>
          </NFormItem>
        </NForm>

        <NDivider />

        <!-- === 修改密码 === -->
        <NForm v-if="!pwdLocked">
          <NFormItem label="原密码">
            <NInput
              v-model:value="oldPassword"
              type="password"
              show-password-on="click"
              placeholder="当前密码"
              style="max-width: 320px"
            />
          </NFormItem>
          <NFormItem label="新密码">
            <NInput
              v-model:value="newPassword"
              type="password"
              show-password-on="click"
              placeholder="大写 + 小写 + 数字 + 至少 8 位"
              style="max-width: 320px"
            />
          </NFormItem>
          <NFormItem label="确认新密码">
            <NSpace style="width: 100%">
              <NInput
                v-model:value="confirmPassword"
                type="password"
                show-password-on="click"
                placeholder="再输一次"
                style="max-width: 320px"
              />
              <NButton
                type="warning"
                :loading="changingPwd"
                :disabled="!pwdOk"
                @click="doChangePassword"
              >
                修改密码
              </NButton>
            </NSpace>
          </NFormItem>
          <NAlert v-if="pwdChecks.length" type="warning" :bordered="false" style="max-width: 320px">
            新密码要求：{{ pwdChecks.join('、') }}
          </NAlert>
          <NAlert v-else-if="newPassword" type="success" :bordered="false" style="max-width: 320px">
            密码强度符合要求
          </NAlert>
        </NForm>
        <!-- 共享账号：不提供改密入口，只说清楚为什么 -->
        <NAlert v-else type="warning" :bordered="false" style="max-width: 520px">
          {{ PWD_LOCKED_TEXT }}
        </NAlert>

        <NDivider />

        <!-- === 登录会话 === -->
        <NText strong>登录设备</NText>
        <NText depth="3" style="font-size: 12px; display: block; margin-top: 4px">
          看到不认识的设备？直接注销它，那台设备就要重新登录了。
        </NText>

        <NDataTable
          :columns="sessionColumns"
          :data="sessions"
          :row-key="(row) => row.id"
          size="small"
          style="margin-top: 12px"
        >
          <template #empty>
            <NEmpty description="没有其他登录会话" />
          </template>
        </NDataTable>

        <NDivider />

        <!-- === 退出登录 === -->
        <NButton type="error" @click="doLogout">退出登录</NButton>
      </template>
    </NSpin>
  </NCard>
</template>

<style scoped>
:deep(.n-descriptions) {
  margin-bottom: 4px;
}
</style>
