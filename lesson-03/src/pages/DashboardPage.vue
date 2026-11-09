<script setup>
/**
 * DashboardPage — ② 题库首页(仪表盘)
 *
 * 原型：数据概览 + 快捷入口 + 最近编辑
 * 后端 /auth/stats 已提供数据统计，直接用。
 */
import { ref, onMounted, h } from 'vue'
import { NCard, NGrid, NGi, NStatistic, NButton, NSpace, NTag, NEmpty } from 'naive-ui'
import { useRouter } from 'vue-router'
import { getMyStats } from '../api/profile'
import { getRecentQuestions } from '../api/batch'
import { renderMathText } from '../utils/mathRenderer'
import { stripFigurePlaceholder } from '../utils/figurePlaceholder'   // ← lesson-38: 展示去掉【题图】占位
import TaskState from '../components/TaskState.vue'
import { useAsyncTask } from '../composables/useAsyncTask'

const router = useRouter()
const stats = ref(null)
const recent = ref([])

// === 课 32：统一异步状态 ===
// 之前这里 catch 里只 console.error → 老师看到的是一片空白
// （连「服务器炸了」都不知道）。现在走 useAsyncTask：错误有话、失败能重试。
const { loading, error, run, retry } = useAsyncTask(async () => {
  const [statsRes, recentRes] = await Promise.all([
    getMyStats(),
    getRecentQuestions(6),
  ])
  stats.value = statsRes.data
  recent.value = recentRes.data.items || []
})

onMounted(() => {
  run().catch(() => undefined)
})

const SHORTCUTS = [
  { key: 'capture', label: '📷 录题', desc: '上传图片自动识别公式', name: 'capture' },
  { key: 'questions', label: '📚 题库', desc: '浏览和搜索全部题目', name: 'questions' },
  { key: 'papers', label: '📄 组卷', desc: '挑题组卷并导出', name: 'paper-new' },
  { key: 'categories', label: '🗂 分类', desc: '维护章节树', name: 'categories' },
]
</script>

<template>
  <TaskState
    :loading="loading"
    :error="error"
    :empty="!stats?.questions"
    @retry="retry"
  >
    <template #empty>
      <NEmpty description="题库还是空的 —— 先去录几道题吧">
        <template #extra>
          <NButton type="primary" @click="router.push({ name: 'capture' })">去录题</NButton>
        </template>
      </NEmpty>
    </template>

    <div>
      <!-- 数据概览 -->
      <NGrid :cols="3" :x-gap="12" :y-gap="12">
        <NGi>
          <NCard size="small"><NStatistic label="题目总数" :value="stats?.questions ?? 0" /></NCard>
        </NGi>
        <NGi>
          <NCard size="small"><NStatistic label="试卷总数" :value="stats?.papers ?? 0" /></NCard>
        </NGi>
        <NGi>
          <NCard size="small"><NStatistic label="上传图片" :value="stats?.uploads ?? 0" /></NCard>
        </NGi>
      </NGrid>

      <!-- 按学科分布 -->
      <NCard v-if="stats?.by_subject?.length" title="按学科分布" size="small" style="margin-top: 12px">
        <NSpace>
          <NTag v-for="s in stats.by_subject" :key="s.subject" size="small" :bordered="false">
            {{ s.subject }} {{ s.count }}
          </NTag>
        </NSpace>
      </NCard>

      <!-- 最近编辑 -->
      <NCard v-if="recent.length" title="最近编辑" size="small" style="margin-top: 12px">
        <NSpace vertical :size="8">
          <div
            v-for="q in recent"
            :key="q.id"
            class="recent-item"
            @click="router.push({ name: 'question-detail', params: { id: q.id } })"
          >
            <div class="recent-text" v-html="renderMathText(stripFigurePlaceholder(q.content_markdown || q.content_plain))" />
            <div class="recent-meta">
              <NTag size="small" :bordered="false">{{ q.subject }}</NTag>
              <span>{{ new Date(q.updated_at).toLocaleString('zh-CN') }}</span>
            </div>
          </div>
        </NSpace>
      </NCard>

      <!-- 快捷入口 -->
      <NCard title="快捷入口" size="small" style="margin-top: 12px">
        <NGrid :cols="4" :x-gap="12" :y-gap="12">
          <NGi v-for="sc in SHORTCUTS" :key="sc.key">
            <NCard hoverable size="small" style="cursor: pointer" @click="router.push({ name: sc.name })">
              <div style="font-size: 15px; font-weight: 600">{{ sc.label }}</div>
              <div style="font-size: 12px; color: #999; margin-top: 4px">{{ sc.desc }}</div>
            </NCard>
          </NGi>
        </NGrid>
      </NCard>
    </div>
  </TaskState>
</template>

<style scoped>
.recent-item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.recent-item:hover {
  background: #f7f7f7;
}

.recent-text {
  font-size: 14px;
  line-height: 1.7;
  max-height: 3.4em;
  overflow: hidden;
}

.recent-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: #999;
}
</style>
