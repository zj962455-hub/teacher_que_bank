/**
 * 反馈 API 客户端 — lesson-34
 *
 * 五个接口（前三个要登录，后两个仅管理员）：
 *   POST  /api/feedback          提交反馈
 *   GET   /api/feedback          看反馈（普通用户只看自己的，管理员看全部）
 *   PATCH /api/feedback/{id}     改处理状态（仅管理员）
 *   GET   /api/feedback/summary  汇总统计（仅管理员）
 *   GET   /api/feedback/export   导出 markdown / csv（仅管理员）
 *
 * ⚠️ 错误文案不在这里处理 —— 统一走 utils/errors.js 的 parseError()。
 *    后端返回的 detail 已经是人话（“邀请码已过期…”/“反馈内容太短了…”），
 *    直接显示即可。
 */

import { http } from './auth'

/** 类别（固定三样，多了老师选不明白） */
export const CATEGORIES = [
  { value: 'bug', label: '功能异常' },
  { value: 'feature', label: '功能建议' },
  { value: 'other', label: '其它' },
]

/** 处理状态 */
export const STATUSES = [
  { value: 'new', label: '待处理' },
  { value: 'read', label: '已读' },
  { value: 'resolved', label: '已处理' },
]

/**
 * 提交反馈
 * @param {Object} payload
 * @param {string} payload.category - bug / feature / other
 * @param {string} payload.content  - 正文（5–2000 字）
 * @param {string} [payload.page_url] - 提反馈时所在的页面（后端截断到 500）
 * @param {string} [payload.reporter] - 谁提的（共享账号下区分老师；空则后端用 display_name 兜底）
 * @param {string} [payload.contact] - 联系方式（选填：微信 / 手机）
 */
export function submitFeedback(payload) {
  return http.post('/feedback', {
    category: payload.category,
    content: payload.content,
    page_url: payload.page_url || '',
    reporter: payload.reporter || '',
    contact: payload.contact || '',
  })
}

/** 反馈列表（普通用户=自己的，管理员=全部） */
export function listFeedbacks() {
  return http.get('/feedback')
}

/**
 * 改处理状态（仅管理员）
 * @param {number} id - 反馈 id
 * @param {string} status - new / read / resolved
 */
export function updateFeedbackStatus(id, status) {
  return http.patch(`/feedback/${id}`, { status })
}

/**
 * 反馈汇总统计（仅管理员）
 *
 * 老大要拿的「反馈结果」：总数 / 分类分布 / 状态分布 / 提交人聚合。
 * contributors 靠 reporter 区分老师 —— 共享账号下 user_id 全一样。
 */
export function getFeedbackSummary() {
  return http.get('/feedback/summary')
}

/**
 * 导出反馈（仅管理员）
 *
 * @param {string} format - markdown | csv
 * @returns {Promise<Blob>} 原始文件流（csv 自带 BOM，Excel 打开中文不乱码）
 */
export function exportFeedbacks(format = 'markdown') {
  return http.get('/feedback/export', {
    params: { format },
    responseType: 'blob',
  })
}

export default {
  CATEGORIES,
  STATUSES,
  submitFeedback,
  listFeedbacks,
  updateFeedbackStatus,
  getFeedbackSummary,
  exportFeedbacks,
}
