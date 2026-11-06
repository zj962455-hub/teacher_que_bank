/**
 * 章节分类 API 客户端 — lesson-11
 *
 * 为什么单独一个文件
 * ------------------
 * 之前的「章节树」是后端按 subject/grade/difficulty 拼出来的假树
 * （GET /questions/categories），看着像树但改不了、拖不动，也没有真正的归属。
 * 现在后端有 categories 真表，这套接口是它的专属客户端。
 *
 * 树节点结构（后端给的）：
 *   { id, name, parent_id, sort_order, count, own_count, children }
 *   count     = 自己 + 所有子孙的题目数
 *   own_count = 直接挂在这个节点上的题目数
 */

import { http } from './auth'

/** 分类树（含题目统计） */
export function getCategoryTree() {
  return http.get('/categories/')
}

/** 扁平列表（给下拉框用：新建子级 / 改归属 / 批量改分类） */
export function getCategoryFlat() {
  return http.get('/categories/flat')
}

/** 新建分类 —— payload: { name, parent_id } */
export function createCategory(payload) {
  return http.post('/categories/', payload)
}

/** 重命名 / 改父节点 —— payload: { name?, parent_id? } */
export function updateCategory(id, payload) {
  return http.put(`/categories/${id}`, payload)
}

/** 删除（子分类上提一层，题目保留但失去归属） */
export function deleteCategory(id) {
  return http.delete(`/categories/${id}`)
}

/**
 * 拖拽排序：重排同一父级下的兄弟顺序
 * @param {number|null} parentId - 父分类 id，null = 顶层
 * @param {number[]} ids - 该父级下的完整 id 顺序
 */
export function reorderCategories(parentId, ids) {
  return http.post('/categories/reorder', { parent_id: parentId ?? null, ids })
}

/**
 * 后端树节点 → NTree 选项
 *
 * NTree 要的是 { key, label, children }，后端给的是 { id, name, ... }，
 * 这里统一转一次（key 用数字 id，和后端对得上）。
 */
export function toTreeOptions(nodes = []) {
  return nodes.map((n) => ({
    key: n.id,
    label: n.name,
    count: n.count ?? 0,
    own_count: n.own_count ?? 0,
    parent_id: n.parent_id ?? null,
    children: n.children && n.children.length ? toTreeOptions(n.children) : undefined,
  }))
}

/**
 * 扁平列表 → 下拉框选项
 * 后端 flat 返回 [{id, name, parent_id, ...}]，
 * 这里补一条缩进前缀，父级名字做前缀更好认。
 */
export function toFlatOptions(flat = [], parents = new Map()) {
  return flat.map((f) => ({
    label: parents.has(f.parent_id) ? `${parents.get(f.parent_id)} / ${f.name}` : f.name,
    value: f.id,
  }))
}

/**
 * 树 → 扁平列表
 *
 * ⚠️ 课 33 性能：为什么要有这个
 * ---------------------------
 * 列表页原本要**两个请求**才能渲染：
 *   GET /api/categories/       （树）
 *   GET /api/categories/flat   （扁平，给下拉框）
 * 两个接口的数据完全重叠（都是同一张 categories 表），
 * 而树节点里**本来就带 parent_id** —— 扁平列表可以直接从树推出来。
 *
 * 于是每个页面首屏少一次往返。
 */
export function flattenTree(nodes = [], out = []) {
  for (const n of nodes) {
    out.push({
      id: n.id,
      name: n.name,
      parent_id: n.parent_id ?? null,
      sort_order: n.sort_order ?? 0,
    })
    if (n.children && n.children.length) flattenTree(n.children, out)
  }
  return out
}

/** 扁平列表 → 下拉框选项（按父子缩进） */
export function flatToOptions(flat = []) {
  const byId = new Map(flat.map((f) => [f.id, f]))
  const labelOf = (f, seen = new Set()) => {
    // 防环（后端已防，这里再兜一层）
    if (seen.has(f.id)) return f.name
    seen.add(f.id)
    const parent = f.parent_id != null ? byId.get(f.parent_id) : null
    if (!parent) return f.name
    return `${labelOf(parent, seen)} / ${f.name}`
  }
  return flat.map((f) => ({ label: labelOf(f), value: f.id }))
}

export default {
  getCategoryTree,
  getCategoryFlat,
  createCategory,
  updateCategory,
  deleteCategory,
  reorderCategories,
  toTreeOptions,
  toFlatOptions,
  flattenTree,
  flatToOptions,
}
