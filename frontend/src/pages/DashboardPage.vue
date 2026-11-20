<script setup>
/**
 * DashboardPage — ② 题库首页(仪表盘)
 *
 * 原型：数据概览 + 快捷入口 + 最近编辑
 * 后端 /auth/stats 已提供数据统计，直接用。
 *
 * UI 改造（2026-11-20）
 * ------------------
 * 1. 统计卡从 naive-ui 的 NStatistic 换成自绘卡片：
 *    NStatistic 三个数字大小一样、没有图标，看着像一张表；
 *    改成「图标 + 大数字 + 说明」，一眼能扫。
 * 2. 「按学科分布」原来是一堆 tag 挤在卡片左边，右边全是空的 ——
 *    改成横向条形分布，占满卡片宽度，长短一眼可比。
 * 3. 「快捷入口」原来是卡片套卡片（外层 NCard 里又 4 个 NCard），
 *    两层同半径显得脏；改成无边框的图标方块。
 * 4. emoji 图标（📷📚📄🗂）换成统一线性 SVG（AppIcon）。
 */
import { ref, onMounted, computed } from 'vue'
import { NButton, NTag, NEmpty } from 'naive-ui'
import { useRouter } from 'vue-router'
import { getMyStats } from '../api/profile'
import { getRecentQuestions } from '../api/batch'
import { renderMathText } from '../utils/mathRenderer'
import { stripFigurePlaceholder } from '../utils/figurePlaceholder'   // ← lesson-38: 展示去掉【题图】占位
import AppIcon from '../components/AppIcon.vue'
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

/** 三个概览数字 —— 顺序按「最常关心 → 最少关心」排 */
const STAT_CARDS = [
  { key: 'questions', label: '题目总数', icon: 'stack' },
  { key: 'papers', label: '试卷总数', icon: 'file' },
  { key: 'uploads', label: '上传图片', icon: 'image' },
]

/** 学科分布的条长：按最大学科归一化 */
const subjectBars = computed(() => {
  const list = stats.value?.by_subject || []
  if (!list.length) return []
  const max = Math.max(...list.map((s) => s.count), 1)
  return list.map((s) => ({
    subject: s.subject,
    count: s.count,
    percent: Math.round((s.count / max) * 100),
  }))
})

const SHORTCUTS = [
  { key: 'capture', label: '录题', desc: '上传图片自动识别公式', icon: 'scan', name: 'capture' },
  { key: 'questions', label: '题库', desc: '浏览和搜索全部题目', icon: 'stack', name: 'questions' },
  { key: 'papers', label: '组卷', desc: '挑题组卷并导出', icon: 'file', name: 'paper-new' },
  { key: 'categories', label: '分类', desc: '维护章节树', icon: 'folder', name: 'categories' },
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

    <div class="dash">
      <!-- 数据概览 -->
      <div class="tqb-stat-grid">
        <div v-for="card in STAT_CARDS" :key="card.key" class="tqb-stat-card">
          <span class="tqb-stat-icon"><AppIcon :name="card.icon" :size="20" /></span>
          <div>
            <div class="tqb-stat-value">{{ stats?.[card.key] ?? 0 }}</div>
            <div class="tqb-stat-label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <!-- 按学科分布 -->
      <section v-if="subjectBars.length" class="panel">
        <h3 class="tqb-section-title">
          <AppIcon name="chart" :size="16" />
          按学科分布
        </h3>
        <div class="subject-bars">
          <div v-for="s in subjectBars" :key="s.subject" class="subject-row">
            <span class="subject-name">{{ s.subject }}</span>
            <span class="subject-track">
              <span class="subject-fill" :style="{ width: s.percent + '%' }" />
            </span>
            <span class="subject-count">{{ s.count }}</span>
          </div>
        </div>
      </section>

      <!-- 最近编辑 -->
      <section v-if="recent.length" class="panel">
        <h3 class="tqb-section-title">
          <AppIcon name="clock" :size="16" />
          最近编辑
        </h3>
        <ul class="recent-list">
          <li
            v-for="q in recent"
            :key="q.id"
            class="recent-item"
            tabindex="0"
            @click="router.push({ name: 'question-detail', params: { id: q.id } })"
            @keyup.enter="router.push({ name: 'question-detail', params: { id: q.id } })"
          >
            <div
              class="recent-text"
              v-html="renderMathText(stripFigurePlaceholder(q.content_markdown || q.content_plain))"
            />
            <div class="recent-meta">
              <NTag size="small" :bordered="false">{{ q.subject }}</NTag>
              <span>{{ new Date(q.updated_at).toLocaleString('zh-CN') }}</span>
            </div>
          </li>
        </ul>
      </section>

      <!-- 快捷入口 -->
      <section class="panel">
        <h3 class="tqb-section-title">
          <AppIcon name="grid" :size="16" />
          快捷入口
        </h3>
        <div class="shortcut-grid">
          <button
            v-for="sc in SHORTCUTS"
            :key="sc.key"
            type="button"
            class="shortcut"
            @click="router.push({ name: sc.name })"
          >
            <span class="shortcut-icon"><AppIcon :name="sc.icon" :size="18" /></span>
            <span class="shortcut-body">
              <span class="shortcut-label">{{ sc.label }}</span>
              <span class="shortcut-desc">{{ sc.desc }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>
  </TaskState>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--tqb-space-4);
}

/* 一块内容 = 一张卡，卡与卡之间靠间距分组（不靠分隔线） */
.panel {
  padding: var(--tqb-space-5);
  background: var(--tqb-bg-card);
  border: 1px solid transparent;
  border-radius: var(--tqb-radius-lg);
  box-shadow: var(--tqb-shadow-card);
}

.panel > .tqb-section-title {
  margin-bottom: var(--tqb-space-4);
}

/* 学科分布条 */
.subject-bars {
  display: flex;
  flex-direction: column;
  gap: var(--tqb-space-3);
}

.subject-row {
  display: grid;
  grid-template-columns: 64px 1fr 40px;
  align-items: center;
  gap: var(--tqb-space-3);
}

.subject-name {
  font-size: var(--tqb-font-sm);
  color: var(--tqb-text-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subject-track {
  height: 8px;
  border-radius: var(--tqb-radius-full);
  background: var(--tqb-surface-sunken);
  overflow: hidden;
}

.subject-fill {
  display: block;
  height: 100%;
  border-radius: var(--tqb-radius-full);
  background: var(--tqb-primary);
  transition: width var(--tqb-transition);
}

.subject-count {
  font-size: var(--tqb-font-sm);
  font-weight: 600;
  text-align: end;
  font-variant-numeric: tabular-nums;
  color: var(--tqb-text-primary);
}

/* 最近编辑：行式列表，一行一条，最后一行不带分隔线 */
.recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-item {
  padding: var(--tqb-space-3);
  margin: 0 calc(-1 * var(--tqb-space-3));
  border-radius: var(--tqb-radius-md);
  cursor: pointer;
  transition: background var(--tqb-transition);
}

.recent-item:hover {
  background: var(--tqb-bg-hover);
}

.recent-text {
  font-size: var(--tqb-font-base);
  line-height: 1.7;
  color: var(--tqb-text-primary);
  max-height: 3.4em;
  overflow: hidden;
}

.recent-meta {
  display: flex;
  align-items: center;
  gap: var(--tqb-space-2);
  margin-top: var(--tqb-space-2);
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-tertiary);
}

/* 快捷入口：方块按钮，不再卡片套卡片 */
.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--tqb-space-3);
}

.shortcut {
  display: flex;
  align-items: center;
  gap: var(--tqb-space-3);
  padding: var(--tqb-space-3) var(--tqb-space-4);
  border: 1px solid transparent;
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-surface-muted);
  font-family: inherit;
  text-align: start;
  cursor: pointer;
  transition: background var(--tqb-transition), box-shadow var(--tqb-transition),
    transform var(--tqb-transition);
}

.shortcut:hover {
  background: var(--tqb-bg-card);
  box-shadow: var(--tqb-shadow-card);
}

.shortcut-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: var(--tqb-radius-md);
  background: var(--tqb-bg-card);
  color: var(--tqb-primary);
}

.shortcut-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.shortcut-label {
  font-size: var(--tqb-font-base);
  font-weight: 600;
  color: var(--tqb-text-primary);
}

.shortcut-desc {
  font-size: var(--tqb-font-xs);
  color: var(--tqb-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
