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

import { http } from './auth'

/** 创建 axios 实例（统一 baseURL + 超时） */
// ⚠️ 用 auth.js 的共享实例 —— 它会自动注入 Authorization 头。
//    自己 create 出来的实例不带 token → 后端返 401。

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
export function createQuestionFromOcr(taskId, overrides = {}) {
  // overrides: 老师手动改过的分类 {subject, question_type, grade, difficulty}
  // —— 不传就是用后端的 AI 分类
  return http.post(`/questions/from-ocr/${taskId}`, overrides)
}

/** 更新题目 */
export function updateQuestion(id, payload) {
  return http.put(`/questions/${id}`, payload)
}

/** 删除题目 */
export function deleteQuestion(id) {
  return http.delete(`/questions/${id}`)
}

/**
 * 导出题库为 Excel
 * @returns {Promise<string>} 下载的文件名
 */
export async function exportQuestionsExcel() {
  const res = await http.get('/questions/export/excel', { responseType: 'blob' })
  const filename = parseFilename(res.headers['content-disposition'], '我的题库.xlsx')
  triggerDownload(res.data, filename)
  return filename
}

/**
 * 导出全部数据备份（JSON）
 * @returns {Promise<string>} 下载的文件名
 */
export async function exportBackupJson() {
  const res = await http.get('/questions/export/backup', { responseType: 'blob' })
  const filename = parseFilename(res.headers['content-disposition'], '题库备份.json')
  triggerDownload(res.data, filename)
  return filename
}

/** 从 Content-Disposition 解析文件名（后端用 RFC 5987 编码中文名） */
function parseFilename(disposition, fallback) {
  if (!disposition) return fallback
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/)
  if (utf8) return decodeURIComponent(utf8[1])
  const plain = disposition.match(/filename="([^"]+)"/)
  return plain ? plain[1] : fallback
}

/** 触发浏览器下载 blob */
function triggerDownload(data, filename) {
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export default {
  listQuestions,
  getQuestion,
  createQuestion,
  createQuestionFromOcr,
  updateQuestion,
  deleteQuestion,
  exportQuestionsExcel,
  exportBackupJson,
}
