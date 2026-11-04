<script setup>
/**
 * DashboardPage — ② 题库首页(仪表盘)
 *
 * 原型：数据概览 + 快捷入口 + 最近编辑
 * 后端 /auth/stats 已提供数据统计，直接用。
 */
import { ref, onMounted, h } from 'vue'
import { NCard, NGrid, NGi, NStatistic, NButton, NSpace, NTag, NSpin, NEmpty } from 'naive-ui'
import { useRouter } from 'vue-router'
import { getMyStats } from '../api/profile'

const router = useRouter()
const stats = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    stats.value = (await getMyStats()).data
  } catch (e) {
    console.error('统计加载失败:', e.message)
  } finally {
    loading.value = false
  }
})

const SHORTCUTS = [
  { key: 'capture', label: '📷 录题', desc: '上传图片自动识别公式', name: 'capture' },
  { key: 'questions', label: '📚 题库', desc: '浏览和搜索全部题目', name: 'questions' },
  { key: 'papers', label: '📄 组卷', desc: '挑题组卷并导出', name: 'paper-new' },
  { key: 'categories', label: '🗂 分类', desc: '维护章节树', name: 'categories' },
]
</script>

<template>
  <NSpin :show="loading">
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

      <NEmpty v-if="!stats?.questions" description="题库还是空的 —— 先去录几道题吧" style="margin-top: 24px">
        <template #extra>
          <NButton type="primary" @click="router.push({ name: 'capture' })">去录题</NButton>
        </template>
      </NEmpty>
    </div>
  </NSpin>
</template>
