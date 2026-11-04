<script setup>
/**
 * LoginPanel — 登录面板 — lesson-11
 *
 * 为什么是「面板」不是独立页面
 * ---------------------------
 * 单页应用里弹面板比跳路由好：登录完原地继续，
 * 不用记住「我刚才在哪个页面」。
 *
 * 功能
 * ----
 * - 用户名 + 密码登录
 * - 显示后端返回的错误（用户名错 / 密码错 / 账号停用）
 * - 登录成功后通知父组件刷新数据
 */
import { ref } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NButton, NSpace, NText, NAlert, NSpin,
} from 'naive-ui'
import { login } from '../api/auth'
import { message } from '../composables/discreteApi'

const emit = defineEmits(['logged-in'])

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!username.value.trim()) {
    errorMsg.value = '请输入用户名'
    return
  }
  if (!password.value) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  errorMsg.value = ''
  try {
    const data = await login(username.value.trim(), password.value)
    message.success(`欢迎，${data.user.display_name || data.user.username}`)
    password.value = ''          // 密码不留在内存里
    emit('logged-in', data.user)
  } catch (e) {
    // 后端的 detail 是中文文案，直接显示
    errorMsg.value = e.response?.data?.detail || `登录失败：${e.message}`
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-panel">
    <NCard title="🔐 教培题库 · 登录" style="max-width: 420px" :bordered="false">
      <NAlert v-if="errorMsg" type="error" :bordered="false" style="margin-bottom: 16px">
        {{ errorMsg }}
      </NAlert>

      <NForm @submit.prevent="handleLogin">
        <NFormItem label="用户名">
          <NInput
            v-model:value="username"
            placeholder="请输入用户名"
            :disabled="loading"
            @keyup.enter="handleLogin"
          />
        </NFormItem>

        <NFormItem label="密码">
          <NInput
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="请输入密码"
            :disabled="loading"
            @keyup.enter="handleLogin"
          />
        </NFormItem>

        <NSpace vertical :size="12">
          <NButton
            type="primary"
            block
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </NButton>
          <NText depth="3" style="font-size: 12px; text-align: center; display: block">
            账号由管理员发放，登录后可在「个人中心」修改密码
          </NText>
        </NSpace>
      </NForm>
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
