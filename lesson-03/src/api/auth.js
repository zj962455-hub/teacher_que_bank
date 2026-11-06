/**
 * 认证客户端 — lesson-11 用户体系
 *
 * 为什么单独一个文件
 * ------------------
 * token 的存取、登录/登出/改密、以及「401 就跳登录页」这套逻辑，
 * 散在各处必然出不一致 —— 所以收口在这里。
 *
 * token 存哪
 * ---------
 * localStorage。理由：
 * - 刷新页面不用重新登录（老师每天用，不该反复输密码）
 * - 同源部署，XSS 风险有限
 * ⚠️ 这是个人内网工具的取舍。真正敏感的站点该用 httpOnly Cookie。
 *
 * 拦截器
 * ------
 * 请求拦截器：自动带上 `Authorization: Bearer <token>`
 * 响应拦截器：401 → 清 token + 抛到全局处理（跳登录）
 */

import axios from 'axios'
import { API } from './config'

const TOKEN_KEY = 'tqb_token'
const USER_KEY = 'tqb_user'

// === token 存取 ===

/** 读 token */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

/** 写 token */
export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

/** 读缓存的用户信息（只用于显示，真实身份以 /auth/me 为准） */
export function getCachedUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** 写缓存的用户信息 */
export function setCachedUser(user) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

/** 清掉登录态 */
export function clearAuth() {
  setToken('')
  setCachedUser(null)
}

// === 401 处理 ===

/**
 * 401 回调
 *
 * 不用 window.location 硬跳 —— 那会丢掉当前页面状态。
 * 交给 App.vue 监听，把登录面板显示出来（单页应用内切换）。
 */
let onUnauthorized = null

/** 注册 401 回调（App.vue 调一次） */
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function handleUnauthorized() {
  clearAuth()
  if (onUnauthorized) onUnauthorized()
}

// === 共享 axios 实例 ===

/**
 * 所有业务请求都用这个实例
 *
 * ⚠️ 组件里如果自己 `axios.get(...)` 就不会带 token → 401。
 *    所以组件必须用这里的 http，或用本文件导出的方法。
 */
export const http = axios.create({
  baseURL: API,
  timeout: 30000,   // PDF 导出要启 Chromium，给足时间
})

// 请求：自动带 token
http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应：401 → 清登录态
http.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      handleUnauthorized()
    }
    return Promise.reject(error)
  },
)

// === 接口 ===

/** 登录 */
export async function login(username, password) {
  const res = await http.post('/auth/login', { username, password })
  setToken(res.data.token)
  setCachedUser(res.data.user)
  return res.data
}

/**
 * 邀请码自助注册（课 34 · 灰度试用入口）
 *
 * ⚠️ 注册成功**直接签发会话** —— 后端把 token 一起返回，
 *    所以这里跟 login 一样：存 token + 存用户，前端不用再登一次。
 *
 * 失败时后端给的是中文 detail（“邀请码已过期，请联系管理员重新获取”），
 *    由 parseError() 取出直接显示 —— 不在这里自己判断 code。
 */
export async function register({ username, password, display_name = '', invite_code }) {
  const res = await http.post('/auth/register', {
    username,
    password,
    display_name,
    invite_code,
  })
  setToken(res.data.token)
  setCachedUser(res.data.user)
  return res.data
}

/** 登出 */
export async function logout() {
  try {
    await http.post('/auth/logout')
  } catch {
    // 后端登出失败也要清本地 —— 本地清理不能依赖网络
  }
  clearAuth()
}

/** 拉当前用户（启动时校验 token 是否还有效） */
export async function fetchMe() {
  const res = await http.get('/auth/me')
  setCachedUser(res.data)
  return res.data
}

/** 修改密码 */
export async function changePassword(oldPassword, newPassword) {
  const res = await http.post('/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
  return res.data
}

// === 鉴权图片 ===

/**
 * 取一张需鉴权图片的 blob URL
 *
 * 为什么不能直接用 <img src="...">
 * --------------------------------
 * 图片接口要 Authorization 头，而 <img src> **带不了自定义头**。
 * 所以只能：先用 axios（带 token）取 blob，再转成 objectURL 给 img 用。
 *
 * ⚠️ 用完要 revokeObjectURL，否则 blob 一直占内存。
 *
 * @param {string} url - 后端返回的 URL（相对路径即可）
 * @returns {Promise<string>} blob: 开头的临时 URL
 */
export async function fetchImageBlobUrl(url) {
  // ⚠️ http 的 baseURL 已经含 /api
  //    后端返回的 url 是完整路径（/api/uploads/xxx），
  //    直接传会变成 /api/api/uploads/xxx —— 这里先剥掉 /api 前缀。
  const path = url.startsWith('/api/') ? url.slice(4) : url
  const res = await http.get(path, { responseType: 'blob' })
  return window.URL.createObjectURL(new Blob([res.data]))
}

export default {
  http,
  getToken,
  setToken,
  getCachedUser,
  setCachedUser,
  clearAuth,
  setUnauthorizedHandler,
  login,
  register,
  logout,
  fetchMe,
  changePassword,
  fetchImageBlobUrl,
}
