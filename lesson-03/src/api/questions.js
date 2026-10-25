/**
 * 题目 API 客户端 — lesson-08
 *
 * 为什么要单独一个 api 文件
 * ----------------------
 * 之前 lesson-04/05/06 的 axios 调用都直接写在组件里，
 * URL 拼在模板字符串里。题目这块有 6 个端点 + 筛选参数，
 * 散在组件里会很难维护 —— 改一次 URL 要翻好几个文件。
 *
 * 统一放这里，组件只管调方法。
 */

import axios from 'axios'

const API = 'http://localhost:8000/api'

/** 创建 axios 实例（统一 baseURL + 超时） */
const http = axios.create({
  baseURL: API,
  timeout: 15000,
})

/**
 * 题目列表
 * @param {object} params - 筛选参数
 *   - subject / question_type / grade / difficulty: 精确匹配
 *   - keyword: 内容关键词（模糊）
 *   - limit / offset: 分页
 */
export function listQuestions(params = {}) {
  return http.get('/questions/', { params })
}

/** 单题详情 */
export function getQuestion(id) {
  return http.get(`/questions/${id}`)
}

/**
 * 新建题目
 * @param {object} payload
 *   - content_plain / content_markdown: 内容两版本
 *   - blocks: OCR blocks 数组
 *   - image_path / ocr_task_id: 来源
 *   - subject / question_type / grade / difficulty: 分类（不传则后端自动分类）
 */
export function createQuestion(payload) {
  return http.post('/questions/', payload)
}

/**
 * 从 OCR 结果一键入库
 * 后端自己读 OCR 记录 + 跑分类器，前端只传 task_id
 * @param {string} taskId - OCR task_id
 */
export function createQuestionFromOcr(taskId) {
  return http.post(`/questions/from-ocr/${taskId}`)
}

/** 更新题目 */
export function updateQuestion(id, payload) {
  return http.put(`/questions/${id}`, payload)
}

/** 删除题目 */
export function deleteQuestion(id) {
  return http.delete(`/questions/${id}`)
}

export default {
  listQuestions,
  getQuestion,
  createQuestion,
  createQuestionFromOcr,
  updateQuestion,
  deleteQuestion,
}
