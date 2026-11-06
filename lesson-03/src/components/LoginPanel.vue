<script setup>
/**
 * LoginPanel — 登录 / 注册面板 — lesson-11 + lesson-34
 *
 * 为什么是「面板」不是独立页面
 * ---------------------------
 * 单页应用里弹面板比跳路由好：登录完原地继续，
 * 不用记住「我刚才在哪个页面」。
 *
 * 两个页签
 * ---------
 * - 登录：管理员发账号 → 老师登录（老流程）
 * - 注册：拿到邀请码 → 自己注册（课 34 灰度试用入口）
 *
 * 注册完**直接进首页**
 * --------------------
 * 后端注册成功就把会话签发了（返回 token），所以这里跟登录一样：
 * 存 token + 存用户 → emit('logged-in')，不多一次「再登一遍」。
 *
 * 错误提示
 * --------
 * 统一走 parseError()（课 32）：后端返回的 detail 已经是人话
 * （“邀请码不存在，请检查是否输错” / “密码不合规：至少一个大写字母”），
 * 直接显示，不用自己猜 code。
 */
import { ref, computed } from 'vue'
import {
  NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NButton, NSpace, NText, NAlert,
} from 'naive-ui'
import { login, register } from '../api/auth'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'

const emit = defineEmits(['logged-in'])

const tab = ref('login')

const username = ref('')
const password = ref('')
const displayName = ref('')
const inviteCode = ref('')

// 客户端校验的提示（不是后端返回的错误）
const hint = ref('')

// === 登录 ===
const {
  loading: loginLoading,
  error: loginError,
  run: runLogin,
  clearError: clearLoginError,
} = useAsyncTask(
  async () => {
    const data = await login(username.value.trim(), password.value)
    password.value = ''          // 密码不留在内存里
    return data
  },
  {
    onSuccess: (data) => {
      message.success(`欢迎，${data.user.display_name || data.user.username}`)
      emit('logged-in', data.user)
    },
  },
)

// === 注册（邀请码） ===
const {
  loading: regLoading,
  error: regError,
  run: runRegister,
  clearError: clearRegError,
} = useAsyncTask(
  async () => {
    const data = await register({
      username: username.value.trim(),
      password: password.value,
      display_name: displayName.value.trim(),
      invite_code: inviteCode.value.trim(),
    })
    password.value = ''
    return data
  },
  {
    onSuccess: (data) => {
      message.success(`注册成功，欢迎加入，${data.user.display_name || data.user.username}`)
      emit('logged-in', data.user)
    },
  },
)

// 当前页签的错误（切页签时别把另一个页签的报错显示出来）
const activeError = computed(() =>
  tab.value === 'login' ? loginError.value : regError.value,
)

function switchTab(name) {
  tab.value = name
  hint.value = ''
}

async function handleLogin() {
  hint.value = ''
  clearLoginError()
  if (!username.value.trim()) {
    hint.value = '请输入用户名'
    return
  }
  if (!password.value) {
    hint.value = '请输入密码'
    return
  }
  try {
    await runLogin()
  } catch {
    // 错误已经由 useAsyncTask 收进 error（页面上直接显示），这里不用再处理
  }
}

async function handleRegister() {
  hint.value = ''
  clearRegError()
  if (!username.value.trim()) {
    hint.value = '请输入用户名'
    return
  }
  if (!password.value) {
    hint.value = '请输入密码'
    return
  }
  if (!inviteCode.value.trim()) {
    hint.value = '请输入邀请码（没有邀请码请找管理员领取）'
    return
  }
  try {
    await runRegister()
  } catch {
    // 同上：邀请码失效/已用尽/用户名重复的文案都在 error.message 里
  }
}
</script>

<template>
  <div class="login-panel">
    <NCard title="🔐 教培题库" style="max-width: 420px" :bordered="false">
      <NTabs v-model:value="tab" type="line" animated @update:value="switchTab">
        <!-- === 登录 === -->
        <NTabPane name="login" tab="登录">
          <NAlert v-if="hint || activeError" type="error" :bordered="false" style="margin-bottom: 16px">
            {{ hint || activeError?.message }}
          </NAlert>

          <NForm @submit.prevent="handleLogin">
            <NFormItem label="用户名">
              <NInput
                v-model:value="username"
                placeholder="请输入用户名"
                :disabled="loginLoading"
                @keyup.enter="handleLogin"
              />
            </NFormItem>

            <NFormItem label="密码">
              <NInput
                v-model:value="password"
                type="password"
                show-password-on="click"
                placeholder="请输入密码"
                :disabled="loginLoading"
                @keyup.enter="handleLogin"
              />
            </NFormItem>

            <NSpace vertical :size="12">
              <NButton
                type="primary"
                block
                :loading="loginLoading"
                @click="handleLogin"
              >
                登录
              </NButton>
              <NText depth="3" style="font-size: 12px; text-align: center; display: block">
                账号由管理员发放，登录后可在「个人中心」修改密码
              </NText>
            </NSpace>
          </NForm>
        </NTabPane>

        <!-- === 注册（邀请码） === -->
        <NTabPane name="register" tab="注册">
          <NAlert v-if="hint || activeError" type="error" :bordered="false" style="margin-bottom: 16px">
            {{ hint || activeError?.message }}
          </NAlert>

          <NForm @submit.prevent="handleRegister">
            <NFormItem label="邀请码">
              <NInput
                v-model:value="inviteCode"
                placeholder="管理员发给你的邀请码"
                :disabled="regLoading"
                @keyup.enter="handleRegister"
              />
            </NFormItem>

            <NFormItem label="用户名">
              <NInput
                v-model:value="username"
                placeholder="登录用的用户名"
                :disabled="regLoading"
                @keyup.enter="handleRegister"
              />
            </NFormItem>

            <NFormItem label="显示名（选填）">
              <NInput
                v-model:value="displayName"
                placeholder="同事看到的名字，留空就用用户名"
                :disabled="regLoading"
                @keyup.enter="handleRegister"
              />
            </NFormItem>

            <NFormItem label="密码">
              <NInput
                v-model:value="password"
                type="password"
                show-password-on="click"
                placeholder="大写 + 小写 + 数字 + 至少 8 位"
                :disabled="regLoading"
                @keyup.enter="handleRegister"
              />
            </NFormItem>

            <NSpace vertical :size="12">
              <NButton
                type="primary"
                block
                :loading="regLoading"
                @click="handleRegister"
              >
                注册并进入
              </NButton>
              <NText depth="3" style="font-size: 12px; text-align: center; display: block">
                试用邀请码由管理员发放 —— 没有邀请码请找管理员要一个
              </NText>
            </NSpace>
          </NForm>
        </NTabPane>
      </NTabs>
    </NCard>
  </div>
</template>

<style scoped>
.login-panel {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
  padding: 24px 16px;
}
</style>
