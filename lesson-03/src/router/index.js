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
    // 公开分享页（课 24）—— 唯一不用登录的业务页
    // ⚠️ meta.public 让路由守卫放行（不跳登录页）
    // ⚠️ meta.standalone 让 App.vue 不套顶栏、不套登录门禁
    path: '/share/:token',
    name: 'shared-paper',
    component: () => import('../pages/SharedPaperPage.vue'),
    meta: { public: true, standalone: true, title: '试卷分享' },
  },
  {
    path: '/feedbacks',
    name: 'feedbacks',
    component: () => import('../pages/FeedbacksPage.vue'),
    meta: { title: '反馈记录' },
  },
  {
    // 老师使用指南（课 34）—— 写给第一次用的老师，纯前端页
    // ⚠️ 不套 meta.adminOnly：每个老师都要能看
    path: '/guide',
    name: 'guide',
    component: () => import('../pages/GuidePage.vue'),
    meta: { title: '使用指南' },
  },
  {
    // 邀请码管理（课 34）—— 仅管理员
    // ⚠️ 前端只是「不给非管理员显示入口」；真正的门在后端
    //    （require_admin → 403）。非管理员手打 URL 进来只能看到空列表 + 报错。
    path: '/invites',
    name: 'invites',
    component: () => import('../pages/InvitesPage.vue'),
    meta: { title: '邀请码管理', adminOnly: true },
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

// === 页面标题：跟着路由走 ===
// ⚠️ 之前 meta.title 是摆设 —— 全站标题永远是 index.html 里的 "Vite App"。
//    老师开多个标签页分不清自己在哪；把试卷链接发到班级群，
//    微信卡片标题也是 "Vite App"（微信抓的是 document.title）。
//
//    格式：<页面名> · 蓝狐题库
//    分享页（/share/:token）单独处理 —— 那页站在外面，
//    标题写「XX 的试卷 · 蓝狐题库」比「试卷分享」有信息量。
const SITE_NAME = '蓝狐题库'
router.afterEach((to) => {
  const page = to.meta?.title
  document.title = page ? `${page} · ${SITE_NAME}` : SITE_NAME
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
