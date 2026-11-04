/**
 * 路由表 — lesson-11 页面拆分
 *
 * 为什么要拆
 * ----------
 * 之前所有功能挤在一个 App.vue 长页面里。MVP 原型是 9 个独立页面，
 * 现在按原型拆开，UI 重写时只需要换视图层，不用推倒重来。
 *
 * 路由守卫
 * --------
 * 未登录一律跳登录页 —— 后端接口都要 Authorization 头，
 * 未登录访问业务页只会拿到一堆 401 白屏。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../pages/LoginPage.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../pages/DashboardPage.vue'),
    meta: { title: '题库首页' },
  },
  {
    path: '/questions',
    name: 'questions',
    component: () => import('../pages/QuestionsPage.vue'),
    meta: { title: '题目列表' },
  },
  {
    path: '/questions/new',
    name: 'question-new',
    component: () => import('../pages/CapturePage.vue'),
    meta: { title: '新建题目' },
  },
  {
    path: '/questions/:id',
    name: 'question-detail',
    component: () => import('../pages/QuestionDetailPage.vue'),
    meta: { title: '题目详情' },
  },
  {
    path: '/capture',
    name: 'capture',
    component: () => import('../pages/CapturePage.vue'),
    meta: { title: '录题' },
  },
  {
    path: '/categories',
    name: 'categories',
    component: () => import('../pages/CategoriesPage.vue'),
    meta: { title: '分类管理' },
  },
  {
    path: '/papers',
    name: 'papers',
    component: () => import('../pages/PaperListPage.vue'),
    meta: { title: '我的试卷' },
  },
  {
    path: '/papers/new',
    name: 'paper-new',
    component: () => import('../pages/PapersPage.vue'),
    meta: { title: '组卷' },
  },
  {
    path: '/papers/:id/export',
    name: 'paper-export',
    component: () => import('../pages/PaperExportPage.vue'),
    meta: { title: '试卷导出' },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('../pages/ProfilePage.vue'),
    meta: { title: '个人中心' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// === 守卫：未登录去登录页 ===
router.beforeEach((to) => {
  if (to.meta.public) {
    // 已登录就别停在登录页
    if (to.name === 'login' && getToken()) return { name: 'dashboard' }
    return true
  }
  if (!getToken()) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  }
  return true
})

export default router
