<script setup>
/**
 * PaperListPage — 我的试卷列表
 *
 * 原型里「我的试卷」在小程序端，Web 端是组卷页里的试卷区。
 * 这里单独给一页列出现有试卷，方便管理。
 */
import { ref, onMounted } from 'vue'
import { NCard, NButton, NSpace, NTag, NSpin, NEmpty, NDataTable } from 'naive-ui'
import { useRouter } from 'vue-router'
import { listPapers, deletePaper } from '../api/papers'
import { dialog } from '../composables/discreteApi'

const router = useRouter()

const papers = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const res = await listPapers()
    papers.value = res.data.items || []
  } catch (e) {
    console.error('试卷列表加载失败:', e.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function doDelete(row) {
  dialog.warning({
    title: `删除「${row.title}」？`,
    content: '删了就找不回来了。',
    positiveText: '确认删除',
    negativeText: '再想想',
    onPositiveClick: async () => {
      try {
        await deletePaper(row.id)
        load()
      } catch (e) {
        console.error('删除失败:', e.message)
      }
    },
  })
}
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">📄 我的试卷</h2>
      <NButton type="primary" size="small" @click="router.push({ name: 'paper-new' })">
        + 组卷
      </NButton>
    </div>

    <NSpin :show="loading">
      <NEmpty v-if="!loading && papers.length === 0" description="还没有试卷">
        <template #extra>
          <NButton type="primary" @click="router.push({ name: 'paper-new' })">去组卷</NButton>
        </template>
      </NEmpty>

      <NSpace v-else vertical :size="12">
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
    </NSpin>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  font-size: 18px;
}

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
