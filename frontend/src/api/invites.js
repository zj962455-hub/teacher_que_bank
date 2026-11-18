/**
 * 邀请码管理 API 客户端 — lesson-34
 *
 * 三个接口（**全部要管理员身份**，后端 require_admin 挡着）：
 *   GET   /api/auth/invites        邀请码列表
 *   POST  /api/auth/invites        生成邀请码
 *   PATCH /api/auth/invites/{id}   启停 / 改名额
 *
 * ⚠️ 这个文件只给管理员入口用 —— 前端隐藏按钮只是「界面不给你看」，
 *    真正的门在后端（普通用户调这些接口拿 403）。
 */

import { http } from './auth'

/** 邀请码列表 */
export function listInvites() {
  return http.get('/auth/invites')
}

/**
 * 生成邀请码
 * @param {Object} payload
 * @param {string} [payload.label] - 备注（给谁发的 / 哪个批次）
 * @param {number} [payload.max_uses] - 名额（默认 1）
 * @param {number} [payload.expires_days] - 多少天后过期（0 = 永不过期）
 */
export function createInvite(payload = {}) {
  return http.post('/auth/invites', {
    label: payload.label || '',
    max_uses: payload.max_uses ?? 1,
    expires_days: payload.expires_days ?? 30,
  })
}

/**
 * 改邀请码
 * @param {number} id - 邀请码 id
 * @param {Object} payload - { is_active?, max_uses?, label? }
 */
export function updateInvite(id, payload) {
  return http.patch(`/auth/invites/${id}`, payload)
}

export default {
  listInvites,
  createInvite,
  updateInvite,
}
