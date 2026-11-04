<script setup>
/**
 * LoginPage — ① 登录页
 *
 * 原型是独立页面（不是弹窗）—— 现在按原型对齐。
 * 登录逻辑都在 LoginPanel 里，这里只负责摆位置。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import LoginPanel from '../components/LoginPanel.vue'
import SiteFooter from '../components/SiteFooter.vue'

const router = useRouter()
const redirect = ref(router.currentRoute.value.query.redirect || '/')

function onLoggedIn() {
  router.replace(redirect.value)
}
</script>

<template>
  <div class="login-page">
    <LoginPanel @logged-in="onLoggedIn" />
    <SiteFooter />
  </div>
</template>

<style scoped>
.login-page {
  min-height: 70vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
</style>
