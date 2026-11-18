/**
 * 举报 API 客户端 — lesson-43
 *
 * 四条线：
 *   POST  /api/reports                 提交举报（**可匿名**，公开渠道）
 *   GET   /api/reports/track/{no}      凭受理编号查进展（举报人自己查）
 *   GET   /api/reports                 举报列表（仅管理员）
 *   GET   /api/reports/summary         状态统计（仅管理员）
 *   PATCH /api/reports/{id}            受理 / 处置（仅管理员）
 *
 * ⚠️ 提交用**独立 axios 实例**（不带 401 拦截器）：
 *    公开分享页的访客没有登录态，如果走 auth.js 的 http 实例，
 *    一旦后端返 401 就会把用户踢下线 —— 但访客本来就没登录，
 *    「踢下线」没意义，还会顺手清掉本地 token。
 *    这里既不注入 token 也不挂 401 处理，提交失败就当普通错误提示。
 */

import axios from 'axios'
import { API } from './config'
import { getToken } from './auth'

/** 举报用的实例：带 token（如果有），但不处理 401 */
const reportHttp = axios.create({
  baseURL: API,
  timeout: 30000,
})

reportHttp.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})

/** 举报理由（与后端 REASONS 一一对应） */
export const REASONS = [
  { value: 'illegal', label: '违法违规内容' },
  { value: 'fraud', label: '诈骗或黑产引流' },
  { value: 'porn', label: '色情低俗' },
  { value: 'violence', label: '暴力恐怖' },
  { value: 'copyright', label: '侵犯知识产权' },
  { value: 'other', label: '其他' },
]

/** 处置状态 */
export const STATUSES = [
  { value: 'pending', label: '待受理' },
  { value: 'processing', label: '核实中' },
  { value: 'resolved', label: '已处置' },
  { value: 'rejected', label: '不予受理' },
]

/** 可被举报的对象类型 */
export const TARGET_TYPES = [
  { value: 'question', label: '题目' },
  { value: 'paper', label: '试卷' },
  { value: 'share', label: '分享链接内容' },
  { value: 'upload', label: '图片' },
  { value: 'user', label: '账号' },
  { value: 'other', label: '其他' },
]

/** 处置动作（管理员用） */
export const DISPOSE_ACTIONS = [
  { value: 'none', label: '仅记录（不执行动作）' },
  { value: 'delete_question', label: '删除被举报题目' },
  { value: 'revoke_share', label: '吊销被举报分享链接' },
  { value: 'disable_account', label: '停用被举报账号' },
]

/**
 * 提交举报（可匿名）
 * @param {Object} payload
 * @returns {Promise} 响应里带 report_no（受理编号）
 */
export function submitReport(payload) {
  return reportHttp.post('/reports', {
    target_type: payload.target_type || 'other',
    target_id: payload.target_id || null,
    target_desc: payload.target_desc || '',
    reason: payload.reason || 'other',
    detail: payload.detail || '',
    reporter_name: payload.reporter_name || '',
    reporter_contact: payload.reporter_contact || '',
  })
}

/** 凭受理编号查处理进展 */
export function trackReport(reportNo) {
  return reportHttp.get('/reports/track/' + encodeURIComponent(reportNo))
}

/** 举报列表（仅管理员） */
export function listReports(params) {
  return reportHttp.get('/reports', { params })
}

/** 举报状态统计（仅管理员） */
export function getReportSummary() {
  return reportHttp.get('/reports/summary')
}

/**
 * 受理 / 处置一条举报（仅管理员）
 * @param {number} id
 * @param {Object} payload - { status, handle_note, dispose_action }
 */
export function handleReport(id, payload) {
  return reportHttp.patch('/reports/' + id, {
    status: payload.status,
    handle_note: payload.handle_note || '',
    dispose_action: payload.dispose_action || 'none',
  })
}

export default {
  REASONS,
  STATUSES,
  TARGET_TYPES,
  DISPOSE_ACTIONS,
  submitReport,
  trackReport,
  listReports,
  getReportSummary,
  handleReport,
}
