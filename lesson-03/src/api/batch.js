/**
 * 批量操作 + 分类树 API 客户端 — lesson-11
 *
 * 批量接口只作用于**当前用户自己的**题目 —— 后端会跳过别人的 id
 * （不当成错误，返回 skipped 数量）。
 */

import { http } from './auth'

/** 分类树（章节树数据源） */
export function getCategoryTree() {
  return http.get('/questions/categories')
}

/** 批量删除题目 */
export function batchDeleteQuestions(ids) {
  return http.post('/questions/batch/delete', { ids })
}

/** 批量改分类/难度（只传要改的字段） */
export function batchUpdateQuestions(ids, patch) {
  return http.post('/questions/batch/update', { ids, ...patch })
}

/** 最近编辑的题目（仪表盘用） */
export function getRecentQuestions(limit = 6) {
  return http.get('/questions/recent', { params: { limit } })
}

export default {
  getCategoryTree,
  batchDeleteQuestions,
  batchUpdateQuestions,
  getRecentQuestions,
}
