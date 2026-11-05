<script setup>
/**
 * PaperListPage — 我的试卷列表
 *
 * 原型里「我的试卷」在小程序端，Web 端是组卷页里的试卷区。
 * 这里单独给一页列出现有试卷，方便管理。
 */
import { ref, onMounted } from 'vue'
import { NCard, NButton, NSpace, NTag, NEmpty } from 'naive-ui'
import { useRouter } from 'vue-router'
import { listPapers, deletePaper } from '../api/papers'
import { dialog, message } from '../composables/discreteApi'
import TaskState from '../components/TaskState.vue'
import { useAsyncTask } from '../composables/useAsyncTask'
import { parseError } from '../utils/errors'

const router = useRouter()

const papers = ref([])

// === 课 32：统一异步状态 ===
// 删除失败之前只 console.error → 老师点了删除，列表纹丝不动，也不知道为什么。
// 现在：删除失败弹 toast 说明原因，列表加载失败给「重试」。
const { loading, error, run, retry } = useAsyncTask(async () => {
  const res = await listPapers()
  papers.value = res.data.items || []
})

onMounted(() => {
  run().catch(() => undefined)
})

function doDelete(row) {
  dialog.warning({
    title: `删除「${row.title}」？`,
    content: '删了就找不回来了。',
    positiveText: '确认删除',
    negativeText: '再想想',
    onPositiveClick: async () => {
      try {
        await deletePaper(row.id)
        message.success('已删除')
        run().catch(() => undefined)
      } catch (e) {
        // ⚠️ 之前是 console.error → 老师点了没反应也不知道原因
        message.error(parseError(e).message)
      }
    },
  })
}
</script>

<template>
  <div>
    <div class="tqb-page-head">
      <h2 class="tqb-page-title">📄 我的试卷</h2>
      <NButton type="primary" size="small" @click="router.push({ name: 'paper-new' })">
        + 组卷
      </NButton>
    </div>

    <TaskState
      :loading="loading"
      :error="error"
      :empty="papers.length === 0"
      @retry="retry"
    >
      <template #empty>
        <NEmpty description="还没有试卷">
          <template #extra>
            <NButton type="primary" @click="router.push({ name: 'paper-new' })">去组卷</NButton>
          </template>
        </NEmpty>
      </template>

      <NSpace vertical :size="12">
        <NCard v-for="p in papers" :key="p.id" size="small">
          <div class="paper-row">
            <div>
              <div class="paper-title">{{ p.title }}</div>
              <div class="paper-meta">
                {{ p.question_count }} 题
                <span v-if="p.subtitle">· {{ p.subtitle }}</span>
                · {{ new Date(p.created_at).toLocaleDateString('zh-CN') }}
              </div>
            </div>
            <NSpace>
              <NButton size="tiny" @click="router.push({ name: 'paper-export', params: { id: p.id } })">
                导出
              </NButton>
              <NButton size="tiny" type="error" @click="doDelete(p)">删除</NButton>
            </NSpace>
          </div>
        </NCard>
      </NSpace>
    </TaskState>
  </div>
</template>

<style scoped>

.paper-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.paper-title {
  font-weight: 600;
}

.paper-meta {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}
</style>
