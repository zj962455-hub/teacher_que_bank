/**
 * 试卷 API 客户端 — lesson-09
 */

import axios from 'axios'
import { API } from './config'

const http = axios.create({
  baseURL: API,
  timeout: 30000,   // PDF 导出要启 Chromium,给足时间
})

/** 试卷列表 */
export function listPapers() {
  return http.get('/papers/')
}

/** 新建试卷 */
export function createPaper(payload) {
  return http.post('/papers/', payload)
}

/** 试卷详情 */
export function getPaper(id) {
  return http.get(`/papers/${id}`)
}

/** 更新试卷（标题/副标题） */
export function updatePaper(id, payload) {
  return http.put(`/papers/${id}`, payload)
}

/** 删除试卷 */
export function deletePaper(id) {
  return http.delete(`/papers/${id}`)
}

/** 加题到试卷 */
export function addPaperQuestion(paperId, payload) {
  return http.post(`/papers/${paperId}/questions`, payload)
}

/** 改题号/分值/顺序 */
export function updatePaperQuestion(paperId, pqId, payload) {
  return http.put(`/papers/${paperId}/questions/${pqId}`, payload)
}

/** 从试卷移除题 */
export function removePaperQuestion(paperId, pqId) {
  return http.delete(`/papers/${paperId}/questions/${pqId}`)
}

/**
 * 导出 PDF
 *
 * 用 blob 下载（不是普通 axios 请求），否则会拿到 JSON 而不是文件
 */
export async function exportPaperPdf(paperId, title = 'paper') {
  const res = await http.get(`/papers/${paperId}/export.pdf`, {
    responseType: 'blob',
  })

  // 从 Content-Disposition 解析文件名（后端用 RFC 5987 编码的中文名）
  let filename = `${title}.pdf`
  const disposition = res.headers['content-disposition'] || ''
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/)
  if (match) {
    filename = decodeURIComponent(match[1])
  } else {
    const plain = disposition.match(/filename="([^"]+)"/)
    if (plain) filename = plain[1]
  }

  // 触发浏览器下载
  const url = window.URL.createObjectURL(new Blob([res.data]))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)

  return filename
}

export default {
  listPapers,
  createPaper,
  getPaper,
  updatePaper,
  deletePaper,
  addPaperQuestion,
  updatePaperQuestion,
  removePaperQuestion,
  exportPaperPdf,
}
