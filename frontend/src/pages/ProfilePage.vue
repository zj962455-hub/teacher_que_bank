<script setup>
/**
 * ProfilePage — ⑨ 个人中心
 *
 * 原型：账号 + 订阅 + 数据导出 + 隐私
 * 订阅和隐私还没做，先做账号部分（复用 ProfilePanel）。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ProfilePanel from '../components/ProfilePanel.vue'

const router = useRouter()

function onLoggedOut() {
  router.replace({ name: 'login' })
}
</script>

<template>
  <div>
    <ProfilePanel @logged-out="onLoggedOut" />
  </div>
</template>
