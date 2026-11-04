/**
 * 个人中心 API 客户端 — lesson-11
 *
 * 单独一个文件的原因：个人中心是「账号相关」的一组接口，
 * 和题库/试卷的业务接口不是一回事，分开放以后端加字段时不会互相影响。
 *
 * 所有请求都用 auth.js 的共享 http 实例 —— 自动带 Authorization 头。
 */

import { http } from './auth'

/** 拉当前用户信息 */
export function getMe() {
  return http.get('/auth/me')
}

/** 修改显示名 */
export function updateProfile(payload) {
  return http.patch('/auth/profile', payload)
}

/** 我的数据统计（题目数/试卷数/上传数/按学科分组） */
export function getMyStats() {
  return http.get('/auth/stats')
}

/** 我的登录会话列表 */
export function listMySessions() {
  return http.get('/auth/sessions')
}

/** 注销某个会话（踢掉别的设备） */
export function revokeSession(sessionId) {
  return http.delete(`/auth/sessions/${sessionId}`)
}

export default {
  getMe,
  updateProfile,
  getMyStats,
  listMySessions,
  revokeSession,
}
