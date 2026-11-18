/**
 * 批量操作 API 客户端 — lesson-11
 *
 * 批量接口只作用于**当前用户自己的**题目 —— 后端会跳过别人的 id
 * （不当成错误，返回 skipped 数量）。
 *
 * ⚠️ 章节树接口不在这里 —— 它已经搬到 api/categories.js
 *    （旧的 GET /questions/categories 假树接口后端已删）。
 */

import { http } from './auth'

/** 批量删除题目 */
export function batchDeleteQuestions(ids) {
  return http.post('/questions/batch/delete', { ids })
}

/**
 * 批量改分类/难度（只传要改的字段）
 * 支持 subject / question_type / grade / difficulty / category_id
 */
export function batchUpdateQuestions(ids, patch) {
  return http.post('/questions/batch/update', { ids, ...patch })
}

/** 最近编辑的题目（仪表盘用） */
export function getRecentQuestions(limit = 6) {
  return http.get('/questions/recent', { params: { limit } })
}

export default {
  batchDeleteQuestions,
  batchUpdateQuestions,
  getRecentQuestions,
}
