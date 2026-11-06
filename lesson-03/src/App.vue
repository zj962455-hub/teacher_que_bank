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
import { ref, computed, onMounted, provide } from 'vue'
import { NButton, NConfigProvider, zhCN, dateZhCN } from 'naive-ui'
import { RouterView, useRouter, useRoute } from 'vue-router'
import LoginPanel from './components/LoginPanel.vue'
import SiteFooter from './components/SiteFooter.vue'
import FeedbackModal from './components/FeedbackModal.vue'
import { lightTheme, darkTheme, buildThemeOverrides } from './styles/theme'
import { getToken, getCachedUser, fetchMe, setUnauthorizedHandler } from './api/auth'

const router = useRouter()
const route = useRoute()

// === 深色模式 ===
// ⚠️ 两处都要改，缺一不可：
//    1. documentElement 的 data-theme → 切换我们自己的 CSS 令牌
//    2. NConfigProvider 的 theme → 切换 naive-ui 内置组件主题
//    只改一处的话，页面一半深一半浅。
const THEME_KEY = 'tqb_theme'
const isDark = ref(localStorage.getItem(THEME_KEY) === 'dark')

function applyTheme(dark) {
  isDark.value = dark
  localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light')
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

// 首次挂载就应用（否则刷新后令牌和组件主题对不上）
applyTheme(isDark.value)

function toggleTheme() {
  applyTheme(!isDark.value)
}

const themeOverrides = computed(() => buildThemeOverrides(isDark.value))

const loggedIn = ref(!!getToken())
const currentUser = ref(getCachedUser())

// === 公开页（课 24 分享链接）===
// ⚠️ 分享页**不套登录门禁** —— 老师把链接发到家长群，对方没账号也要能看。
//    所以未登录时不能只渲染 LoginPanel，得给分享页开一条道。
const isStandalone = computed(() => route.meta.standalone === true)

// 启动时校验 token 还有效（本地有 token 但服务端已过期的情况）
onMounted(async () => {
  // 公开分享页：不需要登录态，也不去校 /auth/me
  // （带了失效 token 去校 → 401 拦截器会清登录态，把访客踢去登录页）
  if (isStandalone.value) return
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
// ⚠️ 「邀请码」是管理员入口（课 34）—— 只有 is_admin 才出现在导航里。
//    注意这只是「界面不给你看」，真正的门在后端（require_admin → 403）。
// ⚠️ 「使用指南」放最后 —— 它是给第一次用的老师看的，不是每天都要点的入口，
//    塞在业务入口中间反而没人注意。
const NAV_ITEMS = computed(() => {
  const items = [
    { name: 'dashboard', label: '首页' },
    { name: 'questions', label: '题库' },
    { name: 'capture', label: '录题' },
    { name: 'categories', label: '分类' },
    { name: 'papers', label: '组卷' },
    { name: 'feedbacks', label: '反馈记录' },
    { name: 'guide', label: '使用指南' },
  ]
  if (currentUser.value?.is_admin) {
    items.push({ name: 'invites', label: '邀请码' })
  }
  return items
})

// === 反馈弹窗（课 34）===
// 顶栏点「反馈」弹出来，随手写两句 —— 让人跳去另一个页面再写，多数人会放弃。
const showFeedback = ref(false)

function go(name) {
  router.push({ name })
}
</script>

<template>
  <NConfigProvider
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme="isDark ? darkTheme : lightTheme"
    :theme-overrides="themeOverrides"
  >
    <div class="app">
      <!-- 公开分享页：只渲染视图，不套顶栏、不套登录门禁 -->
      <template v-if="isStandalone">
        <main class="page">
          <RouterView />
        </main>
        <SiteFooter />
      </template>

      <!-- 未登录：只显示登录页 -->
      <template v-else-if="!loggedIn">
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
          <NSpace :size="4" align="center">
            <NButton quaternary size="small" title="遇到问题？提个反馈" @click="showFeedback = true">
              💬 反馈
            </NButton>
            <NButton quaternary size="small" :title="isDark ? '切到浅色' : '切到深色'" @click="toggleTheme">
              {{ isDark ? '🌙' : '☀️' }}
            </NButton>
            <NButton quaternary size="small" @click="go('profile')">
              👤 {{ currentUser?.display_name || currentUser?.username || '我' }}
            </NButton>
          </NSpace>
        </header>

        <main class="page">
          <RouterView />
        </main>

        <!-- 页脚 · ICP 备案号(公安联网备案要求公示) -->
        <SiteFooter />

        <!-- 反馈弹窗（课 34）-->
        <FeedbackModal v-model:show="showFeedback" />
      </template>
    </div>
  </NConfigProvider>
</template>

<style scoped>
.app {
  max-width: var(--tqb-container-max);
  margin: 0 auto;
  padding: var(--tqb-space-4) var(--tqb-space-4) var(--tqb-space-8);
}

/* 顶栏 —— 吸顶，滚动时导航始终可见 */
.top-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--tqb-space-3);
  flex-wrap: wrap;
  min-height: var(--tqb-topbar-height);
  padding: var(--tqb-space-2) 0;
  margin-bottom: var(--tqb-space-4);
  background: var(--tqb-bg-card);
  border-bottom: 1px solid var(--tqb-border);
  box-shadow: var(--tqb-shadow-xs);
}

.top-left {
  display: flex;
  align-items: center;
  gap: var(--tqb-space-4);
  flex-wrap: wrap;
  min-width: 0;
}

.brand {
  font-size: var(--tqb-font-md);
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--tqb-text-primary);
  white-space: nowrap;
}

.nav {
  display: flex;
  gap: var(--tqb-space-1);
  flex-wrap: wrap;
}

.page {
  min-height: 60vh;
}

/* 手机：导航换行独占一行 */
@media (max-width: 768px) {
  .app {
    padding: var(--tqb-space-3) var(--tqb-space-3) var(--tqb-space-6);
  }

  .top-bar {
    margin-bottom: var(--tqb-space-3);
  }

  .brand {
    font-size: var(--tqb-font-base);
  }
}
</style>
