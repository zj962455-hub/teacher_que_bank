<script setup>
/**
 * App.vue — 应用外壳 + 登录门禁
 *
 * 页面结构对齐 MVP 原型（2026-11-05 决策）
 * ----------------------------------------
 * 原型是 9 个独立 Web 页面，现在用 vue-router 拆开：
 *   ① 登录页        ② 题库首页(仪表盘)   ③ 题目列表
 *   ④ 新建题目      ⑤ 题目详情          ⑥ 分类管理
 *   ⑦ 组卷页        ⑧ 试卷预览/导出     ⑨ 个人中心
 *
 * 登录门禁
 * --------
 * 后端所有业务接口都要 Authorization 头，没 token 直接 401。
 * 未登录时只渲染登录页，业务组件**不渲染**（渲染了也全是 401 白屏）。
 */
import { ref, onMounted, provide } from 'vue'
import { NButton, NConfigProvider, zhCN, dateZhCN } from 'naive-ui'
import { RouterView, useRouter, useRoute } from 'vue-router'
import LoginPanel from './components/LoginPanel.vue'
import SiteFooter from './components/SiteFooter.vue'
import { getToken, getCachedUser, fetchMe, setUnauthorizedHandler } from './api/auth'

const router = useRouter()
const route = useRoute()

const loggedIn = ref(!!getToken())
const currentUser = ref(getCachedUser())

// 启动时校验 token 还有效（本地有 token 但服务端已过期的情况）
onMounted(async () => {
  if (!getToken()) return
  try {
    currentUser.value = await fetchMe()
    loggedIn.value = true
  } catch {
    // token 失效 → 拦截器已经清了 + 触发 onUnauthorized
    loggedIn.value = false
  }
})

// 后端返 401 时（token 过期 / 被踢下线）→ 回到登录态
setUnauthorizedHandler(() => {
  loggedIn.value = false
  currentUser.value = null
  if (route.name !== 'login') router.replace({ name: 'login' })
})

function onLoggedIn(user) {
  currentUser.value = user
  loggedIn.value = true
  router.replace({ name: 'dashboard' })
}

// 登出（个人中心里点的，或改密后被踢下线）
function onLoggedOut() {
  loggedIn.value = false
  currentUser.value = null
  router.replace({ name: 'login' })
}

// 个人中心里改了显示名 → 顶栏同步
function onProfileUpdated(user) {
  currentUser.value = user
}

// 顶栏导航
const NAV_ITEMS = [
  { name: 'dashboard', label: '首页' },
  { name: 'questions', label: '题库' },
  { name: 'capture', label: '录题' },
  { name: 'categories', label: '分类' },
  { name: 'papers', label: '组卷' },
]

function go(name) {
  router.push({ name })
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <div class="app">
      <!-- 未登录：只显示登录页 -->
      <template v-if="!loggedIn">
        <LoginPanel @logged-in="onLoggedIn" />
        <SiteFooter />
      </template>

      <!-- 已登录：顶栏 + 路由视图 -->
      <template v-else>
        <header class="top-bar">
          <div class="top-left">
            <span class="brand">📚 教培题库</span>
            <nav class="nav">
              <NButton
                v-for="item in NAV_ITEMS"
                :key="item.name"
                quaternary
                size="small"
                :type="route.name === item.name ? 'primary' : 'default'"
                @click="go(item.name)"
              >
                {{ item.label }}
              </NButton>
            </nav>
          </div>
          <NButton quaternary size="small" @click="go('profile')">
            👤 {{ currentUser?.display_name || currentUser?.username || '我' }}
          </NButton>
        </header>

        <main class="page">
          <RouterView />
        </main>

        <!-- 页脚 · ICP 备案号(公安联网备案要求公示) -->
        <SiteFooter />
      </template>
    </div>
  </NConfigProvider>
</template>

<style scoped>
.app {
  max-width: 1240px;
  margin: 0 auto;
  padding: 16px;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #e8e8e8;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  font-size: 18px;
  font-weight: 600;
}

.nav {
  display: flex;
  gap: 4px;
}

.page {
  min-height: 60vh;
}
</style>
