/**
 * 分享链接 API 客户端 — lesson-24
 *
 * 两条线
 * ------
 * 管理线（要登录）：生成 / 列出 / 吊销
 * 公开线（不用登录）：看卷子、下 PDF / JPG
 *
 * ⚠️ 公开线**不用** auth.js 的共享 http 实例 —— 它带 401 拦截器，
 *    公开接口返 401 时会把用户踢下线（明明只是链接过期，不该清登录态）。
 *    所以这里单独建一个不带拦截器的 axios 实例。
 */

import axios from 'axios'
import { API } from './config'
import { http } from './auth'

/** 公开接口用的实例：只带 baseURL，不注入 token、不处理 401 */
const publicHttp = axios.create({
  baseURL: API,
  timeout: 60000,   // PDF/JPG 导出要启 Chromium，给足时间
})

// ============================================================
// 管理线（要登录）
// ============================================================

/**
 * 生成分享链接
 * @param {number} paperId - 试卷 id
 * @param {number} expireHours - 有效小时数（默认 7 天 = 168）
 */
export function createShare(paperId, expireHours = 168) {
  return http.post(`/papers/${paperId}/shares`, { expire_hours: expireHours })
}

/** 这张卷的分享链接列表（含已过期/已吊销的） */
export function listShares(paperId) {
  return http.get(`/papers/${paperId}/shares`)
}

/** 吊销一条分享链接 */
export function revokeShare(paperId, shareId) {
  return http.delete(`/papers/${paperId}/shares/${shareId}`)
}

// ============================================================
// 公开线（不用登录）
// ============================================================

/** 看共享的卷子（只读） */
export function getSharedPaper(token) {
  return publicHttp.get(`/shares/${token}`)
}

/**
 * 通过分享链接下载文件
 *
 * 用 blob 下载（不是普通请求），否则拿到的是 JSON 而不是文件
 */
async function downloadShared(token, suffix, fallbackName) {
  const res = await publicHttp.get(`/shares/${token}/export.${suffix}`, {
    responseType: 'blob',
  })

  // 从 Content-Disposition 解析文件名（后端用 RFC 5987 编码的中文名）
  let filename = fallbackName
  const disposition = res.headers['content-disposition'] || ''
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/)
  if (match) {
    filename = decodeURIComponent(match[1])
  } else {
    const plain = disposition.match(/filename="([^"]+)"/)
    if (plain) filename = plain[1]
  }

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

/** 通过分享链接下 PDF */
export function downloadSharedPdf(token) {
  return downloadShared(token, 'pdf', 'paper.pdf')
}

/** 通过分享链接下 JPG（每页一张，ZIP） */
export function downloadSharedJpg(token) {
  return downloadShared(token, 'jpg', 'paper.zip')
}

/**
 * 拼完整分享链接
 *
 * 后端只返回 token，不拼 URL —— 前端知道自己的域名，
 * 后端拼要处理反代头（X-Forwarded-Host / Proto），容易拼错。
 */
export function buildShareUrl(token) {
  return `${window.location.origin}/share/${token}`
}

export default {
  createShare,
  listShares,
  revokeShare,
  getSharedPaper,
  downloadSharedPdf,
  downloadSharedJpg,
  buildShareUrl,
}
