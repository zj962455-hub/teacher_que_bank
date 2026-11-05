<script setup>
/**
 * CategoriesPage — ⑥ 章节分类管理
 *
 * 后端用的是 categories **真表**（不是按 subject/grade/difficulty 拼的假树）：
 * - GET    /api/categories/       树 + 每个节点的题目统计
 * - GET    /api/categories/flat   扁平列表
 * - POST   /api/categories/       新建
 * - PUT    /api/categories/{id}   重命名 / 改父节点（后端防环）
 * - DELETE /api/categories/{id}   删除（子分类上提，题目保留但失去归属）
 * - POST   /api/categories/reorder 拖拽排序（同级顺序）
 *
 * 交互：
 * - 拖动节点排序 / 拖进别的节点当子级（不能拖进自己的子孙）
 * - 选中节点 → 右侧面板做 新建子级 / 重命名 / 删除 / 上移 / 下移
 * - 括号里是题目数：count = 自己 + 子孙，own_count = 只算自己
 */
import { ref, computed, onMounted } from 'vue'
import {
  NButton, NSpace, NTree, NInput, NAlert, NEmpty, NSpin, NTag, NCard,
} from 'naive-ui'
import {
  getCategoryTree, getCategoryFlat, createCategory, updateCategory,
  deleteCategory, reorderCategories, toTreeOptions,
} from '../api/categories'
import { message, dialog } from '../composables/discreteApi'
import { parseError } from '../utils/errors'   // ← 课 32:统一错误解析

// === 数据 ===
const rawTree = ref([])          // 后端结构的树
const options = ref([])          // NTree 选项
const flat = ref([])             // 扁平列表
const loading = ref(false)
const selectedId = ref(null)

// === 面板状态 ===
// mode: null=没有编辑中 | 'create'=新建子级 | 'rename'=重命名
const editing = ref({ mode: null, parentId: null, value: '' })

// === 载入 ===
async function loadTree() {
  loading.value = true
  try {
    const [treeRes, flatRes] = await Promise.all([getCategoryTree(), getCategoryFlat()])
    rawTree.value = treeRes.data.tree || []
    flat.value = flatRes.data || []
    options.value = toTreeOptions(rawTree.value)
  } catch (e) {
    message.error(parseError(e).message)
  } finally {
    loading.value = false
  }
}

onMounted(loadTree)

// === 树操作（纯函数，改本地 rawTree） ===
function findNode(nodes, id) {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children) {
      const hit = findNode(n.children, id)
      if (hit) return hit
    }
  }
  return null
}

/** 摘掉节点（连子树一起），返回被摘掉的节点 */
function detach(nodes, id) {
  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].id === id) {
      const [removed] = nodes.splice(i, 1)
      return removed
    }
    if (nodes[i].children) {
      const found = detach(nodes[i].children, id)
      if (found) return found
    }
  }
  return null
}

/** 插回去：parentId=null → 顶层；否则插到该父节点的 children */
function insertNode(nodes, node, parentId, index) {
  if (parentId === null || parentId === undefined) {
    if (index === null || index === undefined) nodes.push(node)
    else nodes.splice(index, 0, node)
    return true
  }
  const parent = findNode(nodes, parentId)
  if (!parent) return false
  if (!parent.children) parent.children = []
  if (index === null || index === undefined) parent.children.push(node)
  else parent.children.splice(index, 0, node)
  return true
}

/** 某父级下的兄弟节点数组 */
function siblingsOf(nodes, parentId) {
  if (parentId === null || parentId === undefined) return nodes
  const p = findNode(nodes, parentId)
  return p?.children || []
}

/** targetId 是不是 ancestorId 的后代（防环） */
function isDescendant(targetId, ancestorId) {
  const ancestor = findNode(rawTree.value, ancestorId)
  if (!ancestor) return false
  return !!findNode(ancestor.children || [], targetId)
}

function refreshOptions() {
  options.value = toTreeOptions(rawTree.value)
}

// === 选中 ===
function onSelect(keys) {
  selectedId.value = keys.length ? keys[0] : null
  editing.value = { mode: null, parentId: null, value: '' }
}

const selectedNode = computed(() =>
  selectedId.value === null ? null : findNode(rawTree.value, selectedId.value),
)

const parentName = computed(() => {
  const p = selectedNode.value?.parent_id
  if (!p) return '顶层'
  return findNode(rawTree.value, p)?.name || '—'
})

// === 新建 / 重命名 ===
function startCreate(parentId) {
  editing.value = { mode: 'create', parentId, value: '' }
}

function startRename() {
  if (!selectedNode.value) return
  editing.value = { mode: 'rename', parentId: null, value: selectedNode.value.name }
}

function cancelEdit() {
  editing.value = { mode: null, parentId: null, value: '' }
}

async function submitEdit() {
  const name = editing.value.value.trim()
  if (!name) {
    message.warning('名字不能为空')
    return
  }
  try {
    if (editing.value.mode === 'create') {
      await createCategory({ name, parent_id: editing.value.parentId })
      message.success('已新建')
    } else {
      await updateCategory(selectedId.value, { name })
      message.success('已重命名')
    }
    cancelEdit()
    await loadTree()
  } catch (e) {
    message.error(parseError(e).message)
  }
}

// === 删除 ===
function confirmDelete() {
  const node = selectedNode.value
  if (!node) return
  dialog.warning({
    title: '删除分类',
    content: `确定删除「${node.name}」？子分类会上提一层，题目会保留但不再归属任何分类。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteCategory(node.id)
        message.success('已删除')
        selectedId.value = null
        cancelEdit()
        await loadTree()
      } catch (e) {
        message.error(parseError(e).message)
      }
    },
  })
}

// === 上移 / 下移 ===
async function moveSibling(delta) {
  const node = selectedNode.value
  if (!node) return
  const parentId = node.parent_id ?? null
  const list = siblingsOf(rawTree.value, parentId)
  const idx = list.findIndex((n) => n.id === node.id)
  const target = idx + delta
  if (idx < 0 || target < 0 || target >= list.length) {
    message.info(delta < 0 ? '已经在最上面了' : '已经在最下面了')
    return
  }
  const ids = list.map((n) => n.id)
  ;[ids[idx], ids[target]] = [ids[target], ids[idx]]
  try {
    await reorderCategories(parentId, ids)
    await loadTree()
  } catch (e) {
    message.error(parseError(e).message)
  }
}

// === 拖拽 ===
function allowDrop({ dropPosition, node, phase }) {
  if (phase === 'drag') return true
  const dragId = draggingId.value
  if (dragId === null) return true
  if (dragId === node.key) return false
  // 不允许拖进自己的子孙（后端也会拦，这里先给提示）
  if (dropPosition === 'inside' && isDescendant(node.key, dragId)) return false
  return true
}

const draggingId = ref(null)

function onDragstart({ node }) {
  draggingId.value = node.key
}

async function onDrop({ node, dragNode, dropPosition }) {
  const dragId = dragNode.key
  const targetId = node.key
  draggingId.value = null
  if (dragId === targetId) return
  if (dropPosition === 'inside' && isDescendant(targetId, dragId)) {
    message.warning('不能把分类拖进它自己的下级')
    return
  }

  const dragged = detach(rawTree.value, dragId)
  if (!dragged) return
  const target = findNode(rawTree.value, targetId)
  if (!target) {
    await loadTree()
    return
  }

  const oldParentId = dragged.parent_id ?? null
  let parentId = target.parent_id ?? null
  let index = siblingsOf(rawTree.value, parentId).findIndex((n) => n.id === targetId)

  if (dropPosition === 'inside') {
    parentId = targetId
    index = siblingsOf(rawTree.value, parentId).length
  } else if (dropPosition === 'after') {
    index = index + 1
  }

  dragged.parent_id = parentId
  insertNode(rawTree.value, dragged, parentId, index)
  refreshOptions()

  try {
    // 换了父级 → 先改归属，再排同级顺序
    if (oldParentId !== parentId) {
      await updateCategory(dragId, { parent_id: parentId })
    }
    await reorderCategories(parentId, siblingsOf(rawTree.value, parentId).map((n) => n.id))
    if (oldParentId !== parentId) {
      await reorderCategories(oldParentId, siblingsOf(rawTree.value, oldParentId).map((n) => n.id))
    }
    await loadTree()
  } catch (e) {
    message.error(parseError(e).message)
    await loadTree()
  }
}

// === 统计 ===
const stats = computed(() => {
  const count = (nodes) => nodes.reduce(
    (sum, n) => sum + (n.own_count || 0) + count(n.children || []), 0,
  )
  const total = flat.value.length
  const questions = count(rawTree.value)
  return { total, questions }
})

// === 节点标签 ===
function renderNodeLabel({ option }) {
  const opt = option || {}
  const own = opt.own_count || 0
  const all = opt.count || 0
  return own === all ? `${opt.label} (${all})` : `${opt.label} (${all} / 本级 ${own})`
}
</script>

<template>
  <div>
    <div class="tqb-page-head">
      <h2 class="tqb-page-title">🗂 章节分类管理</h2>
      <NSpace :size="8">
        <NButton size="small" type="primary" @click="startCreate(null)">+ 新建顶层分类</NButton>
        <NButton size="small" quaternary @click="loadTree">刷新</NButton>
      </NSpace>
    </div>

    <p class="page-desc">
      维护题目归属的章节树。拖动节点可排序，拖到别的节点上可变成它的子级；
      括号里是题目数（全部 / 本级）。
    </p>

    <NSpace :size="8" style="margin-bottom: 12px">
      <NTag type="info" size="small">共 {{ stats.total }} 个分类</NTag>
      <NTag type="success" size="small">已归类 {{ stats.questions }} 道题</NTag>
    </NSpace>

    <div class="tqb-layout">
      <NCard title="章节树" size="small" class="tqb-sidebar">
        <NSpin :show="loading">
          <NTree
            v-if="options.length"
            :data="options"
            :draggable="true"
            default-expand-all
            block-line
            :render-label="renderNodeLabel"
            :allow-drop="allowDrop"
            @update:selected-keys="onSelect"
            @dragstart="onDragstart"
            @drop="onDrop"
          />
          <NEmpty v-else description="还没有分类，先建一个" size="small" />
        </NSpin>
      </NCard>

      <NCard size="small" class="panel-card">
        <template #header>节点操作</template>

        <NEmpty v-if="!selectedNode && !editing.mode" description="先在左边选一个分类" size="small" />

        <!-- 编辑框（新名 / 新建）独立于选中状态 —— 「新建顶层分类」不需要先选节点 -->
        <div v-if="editing.mode" class="edit-row">
          <NInput
            v-model:value="editing.value"
            :placeholder="editing.mode === 'create' ? '新分类名字' : '改名字'"
            size="small"
            autofocus
            @keyup.enter="submitEdit"
          />
          <NButton size="small" type="primary" @click="submitEdit">确定</NButton>
          <NButton size="small" quaternary @click="cancelEdit">取消</NButton>
        </div>

        <template v-else-if="selectedNode">
          <div class="node-info">
            <div class="node-name">{{ selectedNode.name }}</div>
            <NSpace :size="6">
              <NTag size="small" type="info">父级：{{ parentName }}</NTag>
              <NTag size="small">题目 {{ selectedNode.count }}（本级 {{ selectedNode.own_count }}）</NTag>
            </NSpace>
          </div>

          <div v-if="editing.mode" class="edit-row">
            <NInput
              v-model:value="editing.value"
              :placeholder="editing.mode === 'create' ? '新分类名字' : '改名字'"
              size="small"
              autofocus
              @keyup.enter="submitEdit"
            />
            <NButton size="small" type="primary" @click="submitEdit">确定</NButton>
            <NButton size="small" quaternary @click="cancelEdit">取消</NButton>
          </div>

          <NSpace :size="8" style="margin-top: 12px; flex-wrap: wrap">
            <NButton size="small" @click="startCreate(selectedNode.id)">+ 子分类</NButton>
            <NButton size="small" @click="startRename">重命名</NButton>
            <NButton size="small" @click="moveSibling(-1)">上移</NButton>
            <NButton size="small" @click="moveSibling(1)">下移</NButton>
            <NButton size="small" type="error" quaternary @click="confirmDelete">删除</NButton>
          </NSpace>

          <NAlert
            style="margin-top: 12px"
            type="info"
            size="small"
            :bordered="false"
            title="删除的影响"
          >
            子分类会上提一层，题目会保留但不再归属任何分类。
          </NAlert>
        </template>
      </NCard>
    </div>
  </div>
</template>

<style scoped>

.page-desc {
  color: #666;
  font-size: 13px;
  margin: 8px 0 12px;
}

.panel-card {
  flex: 1;
  min-width: 0;
}

.node-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.node-name {
  font-size: 16px;
  font-weight: 600;
}

.edit-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
