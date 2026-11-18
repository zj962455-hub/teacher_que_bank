<script setup>
/**
 * LoginPanel — 登录 / 注册面板 — lesson-11 + lesson-34 + lesson-39
 *
 * lesson-39 改了什么
 * -----------------
 * - 登录：**手机号**作为账号 + 密码（旧的存量账号仍可用原用户名登录）
 * - 注册：**手机号 + 短信验证码** + 密码（替代原来的邀请码注册）
 * - 登录时如果手机号还没注册 → 直接就地跳到注册页签，
 *   不让老师「知道没账号还得自己找入口」。
 *
 * 为什么是面板不是独立页面
 * -------------------------
 * 单页应用里弹面板比跳路由好：登录完原地继续，
 * 不用记住「我刚才在哪个页面」。
 *
 * 错误提示
 * --------
 * 统一走 parseError()（课 32）：后端返回的 detail 已经是人话
 * （「验证码不对或已过期，重新输一下」/「密码不合规：至少一个大写字母」），
 * 直接显示，不用自己猜 code。
 */
import { ref, computed, onUnmounted } from 'vue'
import {
  NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NButton, NSpace, NText, NAlert, NCheckbox,
} from 'naive-ui'
import { login, register, sendSmsCode } from '../api/auth'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'

const emit = defineEmits(['logged-in'])

const tab = ref('login')

// === 登录 ===
const account = ref('')
const password = ref('')

// === 注册 ===
const phone = ref('')
const code = ref('')
const displayName = ref('')
const agreed = ref(false)

// 客户端校验的提示（不是后端返回的错误）
const hint = ref('')

// === 发送验证码倒计时 ===
// ⚠️ 倒计时要跟着组件一起销毁 —— 老师注册到一半切走，
//    定时器还在跑会报错。
const cooldown = ref(0)
let timer = null

function startCooldown(seconds) {
  cooldown.value = seconds
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// === 登录 ===
const {
  loading: loginLoading,
  error: loginError,
  run: runLogin,
  clearError: clearLoginError,
} = useAsyncTask(
  async () => {
    const data = await login(account.value.trim(), password.value)
    password.value = ''          // 密码不留在内存里
    return data
  },
  {
    onSuccess: (data) => {
      message.success(`欢迎，${data.user.display_name || data.user.username}`)
      emit('logged-in', data.user)
    },
    onError: (err) => {
      // 「这个手机号还没注册」→ 就地把他送到注册页签，
      // 手机号都帮他填好了。
      if (err.code === 'auth.account_not_found') {
        phone.value = account.value.trim()
        tab.value = 'register'
        hint.value = '这个手机号还没注册过，用验证码注册一个吧'
      }
    },
  },
)

// === 发验证码 ===
const {
  loading: smsLoading,
  error: smsError,
  run: runSendCode,
  clearError: clearSmsError,
} = useAsyncTask(
  async () => {
    const data = await sendSmsCode(phone.value.trim())
    startCooldown(data.cooldown || 60)
    message.success('验证码已发送，5 分钟内有效')
    return data
  },
)

// === 注册 ===
const {
  loading: regLoading,
  error: regError,
  run: runRegister,
  clearError: clearRegError,
} = useAsyncTask(
  async () => {
    const data = await register({
      phone: phone.value.trim(),
      code: code.value.trim(),
      password: password.value,
      display_name: displayName.value.trim(),
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
const activeError = computed(() => {
  if (tab.value === 'login') return loginError.value
  if (tab.value === 'sms') return smsError.value
  return regError.value
})

function switchTab(name) {
  tab.value = name
  hint.value = ''
  clearLoginError()
  clearSmsError()
  clearRegError()
}

async function handleLogin() {
  hint.value = ''
  clearLoginError()
  if (!account.value.trim()) {
    hint.value = '请输入手机号'
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

async function handleSendCode() {
  hint.value = ''
  clearSmsError()
  const p = phone.value.trim()
  if (!/^1[3-9]\d{9}$/.test(p)) {
    hint.value = '手机号格式不对，检查一下'
    return
  }
  try {
    await runSendCode()
  } catch {
    // 同上：错误显示在页面上
  }
}

async function handleRegister() {
  hint.value = ''
  clearRegError()
  if (!/^1[3-9]\d{9}$/.test(phone.value.trim())) {
    hint.value = '手机号格式不对，检查一下'
    return
  }
  if (!code.value.trim()) {
    hint.value = '请输入短信验证码'
    return
  }
  if (!password.value) {
    hint.value = '请设置密码'
    return
  }
  if (!agreed.value) {
    hint.value = '请先勾选同意接收短信'
    return
  }
  try {
    await runRegister()
  } catch {
    // 同上：错误显示在页面上
  }
}
</script>

<template>
  <div class="login-panel">
    <NCard title="🦊 蓝狐题库" style="max-width: 420px" :bordered="false">
      <NTabs v-model:value="tab" type="line" animated @update:value="switchTab">
        <!-- === 登录 === -->
        <NTabPane name="login" tab="登录">
          <NAlert v-if="hint || activeError" type="error" :bordered="false" style="margin-bottom: 16px">
            {{ hint || activeError?.message }}
          </NAlert>

          <NForm @submit.prevent="handleLogin">
            <NFormItem label="手机号">
              <NInput
                v-model:value="account"
                placeholder="请输入手机号"
                :maxlength="11"
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
                还没有账号？切到「注册」用手机号收验证码注册
              </NText>
            </NSpace>
          </NForm>
        </NTabPane>

        <!-- === 注册（手机号 + 验证码） === -->
        <NTabPane name="register" tab="注册">
          <NAlert v-if="hint || activeError" type="error" :bordered="false" style="margin-bottom: 16px">
            {{ hint || activeError?.message }}
          </NAlert>

          <NForm @submit.prevent="handleRegister">
            <NFormItem label="手机号">
              <NInput
                v-model:value="phone"
                placeholder="请输入手机号"
                :maxlength="11"
                :disabled="regLoading"
                @keyup.enter="handleRegister"
              />
            </NFormItem>

            <NFormItem label="短信验证码">
              <NSpace vertical :size="8">
                <NSpace :size="8" style="width: 100%">
                  <NInput
                    v-model:value="code"
                    placeholder="6 位验证码"
                    :maxlength="6"
                    :disabled="regLoading"
                    style="flex: 1"
                    @keyup.enter="handleRegister"
                  />
                  <NButton
                    :disabled="cooldown > 0 || smsLoading"
                    :loading="smsLoading"
                    style="width: 116px"
                    @click="handleSendCode"
                  >
                    {{ cooldown > 0 ? `${cooldown} 秒后重发` : '获取验证码' }}
                  </NButton>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  短信由阿里云下发，落款是平台赠送签名
                </NText>
              </NSpace>
            </NFormItem>

            <NFormItem label="显示名（选填）">
              <NInput
                v-model:value="displayName"
                placeholder="同事看到的名字，留空自动用手机号打码"
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

            <NFormItem :show-label="false">
              <NCheckbox v-model:checked="agreed" :disabled="regLoading">
                同意接收短信验证码
              </NCheckbox>
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
                注册即用手机号登录 —— 老师不用记用户名
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