/**
 * 标签 API 客户端 — lesson-11
 *
 * 标签 vs 章节分类
 * --------------
 * - 章节（categories）：层级，一题只能属于一个
 * - 标签（tags）：扁平，一题可以打多个（「易错题」「期末冲刺」「需要板书」）
 *
 * 后端接口：
 *   GET    /api/tags/                  列表（带题目数）
 *   POST   /api/tags/                  新建（重名自动复用）
 *   PUT    /api/tags/{id}              重命名 / 改颜色
 *   DELETE /api/tags/{id}              删除（题目保留）
 *   GET    /api/tags/question/{qid}    某题的标签
 *   PUT    /api/tags/question/{qid}    设置某题的标签（整体替换）
 */

import { http } from './auth'

/** 标签列表（含题目数统计） */
export function listTags() {
  return http.get('/tags/')
}

/**
 * 新建标签
 * @param {object} payload - { name, color }
 * @returns 重名时后端返回已有标签（reused: true）
 */
export function createTag(payload) {
  return http.post('/tags/', payload)
}

/** 重命名 / 改颜色 */
export function updateTag(id, payload) {
  return http.put(`/tags/${id}`, payload)
}

/** 删除标签（题目保留，只解除关联） */
export function deleteTag(id) {
  return http.delete(`/tags/${id}`)
}

/** 某题的标签 */
export function getQuestionTags(questionId) {
  return http.get(`/tags/question/${questionId}`)
}

/**
 * 设置某题的标签（整体替换，不是追加）
 * @param {number} questionId
 * @param {number[]} tagIds - 空数组 = 清空所有标签
 */
export function setQuestionTags(questionId, tagIds) {
  return http.put(`/tags/question/${questionId}`, { tag_ids: tagIds })
}
