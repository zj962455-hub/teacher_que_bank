/**
 * 统一错误处理 — lesson-32
 *
 * 课 32 要解决什么
 * ----------------
 * Phase 3 的功能都齐了，但**用起来还是会出两类问题**：
 *
 * 1. **页面崩成白屏** —— 后端 500 / 网络断了 / 参数不对，
 *    前端只 `console.error` 一句就完事，老师看到的是一片空白，
 *    不知道是「服务器炸了」还是「我网不好」。
 * 2. **不知道在 loading** —— 提交按钮点了之后没反馈，
 *    老师以为没点上，又点一次 → 重复提交。
 *
 * 后端这边，所有错误出口现在返回**同一个形状**（lesson-32 改的）：
 *
 * ```json
 * { "detail": "人话说明", "code": "stable_machine_code", "request_id": "a1b2c3d4e5f6" }
 * ```
 *
 * 前端不用再判断 detail 是字符串还是数组，一个函数解析全平台的错误。
 *
 * 关键约束：`detail` 永远是字符串、`code` 稳定、`request_id` 能对上服务端日志。
 */

import axios from 'axios'

// === 机器码 → 人话（前端兜底；后端给了 detail 就用后端的） ===

export const CODE_TEXT = {
  'auth.required': '需要登录',
  'auth.expired': '登录已失效，请重新登录',
  'auth.forbidden': '没有权限',
  'resource.not_found': '内容不存在或已被删除',
  'resource.conflict': '与现有内容冲突',
  'request.validation_failed': '提交的内容有问题',
  'server.internal': '服务器出错了',
  'server.unavailable': '服务暂时不可用',
  'request.failed': '请求失败',
}

// 网络层错误（请求根本没到后端 / 后端没回包）
export const NETWORK_TEXT = {
  timeout: '请求超时了，检查一下网络再试',
  network: '连不上服务器，检查网络或稍后再试',
  canceled: '请求已取消',
}

/**
 * 统一的前端错误对象
 *
 * 为什么要自己封一个类
 * ------------------
 * axios 抛出来的 error 结构很杂：
 * - 网络断了 → `error.request` 有，`error.response` 没有
 * - 后端返 4xx/5xx → `error.response.data.detail`
 * - 超时 → `error.code === 'ECONNABORTED'`
 *
 * 页面里写 `e.response?.data?.detail || \`失败：${e.message}\` 这种代码，
 * 网络错误时就会显示成「失败：Network Error」—— 老师看不懂。
 *
 * 统一成 `{ message, code, requestId, status }` 之后，
 * 页面只写 `error.message` 一句就够。
 */
export class ApiError {
  constructor(message, { code = 'request.failed', request_id = '', status = null, raw = null } = {}) {
    this.message = message
    this.code = code
    this.request_id = request_id
    this.status = status
    this.raw = raw
  }

  get requestId() {
    return this.request_id
  }

  toString() {
    return `ApiError(${this.message}, code=${this.code}, status=${this.status})`
  }
}

/**
 * 从响应体里取 (detail, code, request_id)
 *
 * ⚠️ 必须假设 detail **可能是字符串、可能是数组、可能压根没有**：
 * 后端被网关/反代拦下时返回的是 HTML，不是 JSON。
 */
function _detailFromResponse(response) {
  let data = null
  try {
    data = response.data
  } catch {
    data = null
  }

  if (typeof data === 'string') {
    // 反代/网关返回的 HTML 错误页
    const text = data.trim()
    if (text.startsWith('<')) {
      return ['服务器返回了异常内容（可能网关拦截了）', 'server.unavailable', '']
    }
    return [text.slice(0, 200) || '服务器返回了异常内容', 'server.unavailable', '']
  }

  if (data && typeof data === 'object') {
    const detail = data.detail
    const code = data.code || ''
    const rid = data.request_id || (response.headers && response.headers['X-Request-ID']) || ''

    // detail 可能是数组（老后端开发模式 / FastAPI 默认 422）
    if (Array.isArray(detail)) {
      const first = detail[0] || {}
      const msg = first.msg || String(first)
      return [`提交的内容有问题：${msg}`, code || 'request.validation_failed', rid]
    }
    if (typeof detail === 'string' && detail.trim()) {
      return [detail.trim(), code || 'request.failed', rid]
    }
    if (code && CODE_TEXT[code]) {
      return [CODE_TEXT[code], code, rid]
    }
    return ['服务器返回了未预期的错误', code || 'server.unavailable', rid]
  }

  return ['服务器返回了未预期的错误', 'server.unavailable', '']
}

/**
 * 把任意 catch 到的错误解析成 ApiError
 *
 * 用法：`catch (e) { const err = parseError(e); message.error(err.message) }`
 */
export function parseError(error) {
  // 已经是 ApiError
  if (error instanceof ApiError) return error

  // axios 错误
  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNABORTED' || /timeout/i.test(error.code || '')) {
      return new ApiError(NETWORK_TEXT.timeout, { code: 'request.timeout', raw: error })
    }
    if (error.code === 'ERR_CANCELED') {
      return new ApiError(NETWORK_TEXT.canceled, { code: 'request.canceled', raw: error })
    }
    if (error.response) {
      const [detail, code, rid] = _detailFromResponse(error.response)
      const status = error.response.status
      // 5xx 且后端没给可读 detail → 用兜底文案
      let text = detail
      if (status >= 500 && !CODE_TEXT[code]) {
        text = '服务器出错了，请稍后再试'
      }
      return new ApiError(text, { code, request_id: rid, status, raw: error })
    }
    // 有 request 没 response → 网络层失败
    return new ApiError(NETWORK_TEXT.network, { code: 'request.network', raw: error })
  }

  // 后端用 JSON 字符串抛的普通 Error
  if (error instanceof Error) {
    const text = String(error).trim()
    if (text.startsWith('{')) {
      try {
        const data = JSON.parse(text)
        if (data && data.detail) {
          return new ApiError(String(data.detail), {
            code: data.code || 'request.failed',
            request_id: data.request_id || '',
            raw: error,
          })
        }
      } catch {
        // 不是 JSON,当普通错误处理
      }
    }
    return new ApiError(text || '出了点问题', { raw: error })
  }

  return new ApiError('出了点问题', { raw: error })
}

export default parseError
