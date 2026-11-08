<script setup>
/**
 * QuestionDetailPage — ⑤ 题目详情
 *
 * 原型：单题只读 + 编辑/加入试卷/分享/删除
 * 分享已砍（第一版不做），这里做只读展示 + 编辑 + 删除。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NSpin, NButton, NSpace, NTag, NDivider, NAlert, NSelect, NText } from 'naive-ui'
import { getQuestion, deleteQuestion } from '../api/questions'
import { listTags, getQuestionTags, setQuestionTags } from '../api/tags'
import { dialog, message } from '../composables/discreteApi'
import { renderMathText } from '../utils/mathRenderer'
import { parseError } from '../utils/errors'
import { fetchImageBlobUrl } from '../api/auth'
import QuestionEditor from '../components/QuestionEditor.vue'

const route = useRoute()
const router = useRouter()

const question = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const editing = ref(false)

// === 题图（图形裁剪图） ===
// 图片接口要鉴权 → <img src> 带不了 Authorization 头 → 取 blob
// 以前详情页/列表页都不渲染 figure_path → 老师说「识别到了但是不显示」
const figureBlobUrl = ref('')
const figureFailed = ref(false)

// === 题图排版（老师自定义）===
// 版式存在题上（figure_layout / figure_width），导出试卷时按它排。
const figureLayout = computed(() => question.value?.figure_layout || 'bottom_right')
const figureLayoutClass = computed(() => 'q-' + figureLayout.value)
const figureImgStyle = computed(() => {
  const w = Number(question.value?.figure_width || 0)
  return {
    maxWidth: w > 0 ? w + '%' : '100%',
    border: '1px solid #e0e0e0',
    borderRadius: '4px',
  }
})

async function loadFigure(path) {
  figureBlobUrl.value = ''
  figureFailed.value = false
  if (!path) return
  try {
    figureBlobUrl.value = await fetchImageBlobUrl(path)
  } catch (e) {
    figureFailed.value = true
  }
}

/** 全部标签（选择器用） */
const allTags = ref([])
/** 当前题打上的标签 id */
const questionTagIds = ref([])
/** 标签保存中 */
const savingTags = ref(false)

const questionId = computed(() => route.params.id)

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await getQuestion(questionId.value)
    question.value = res.data
    loadFigure(res.data.figure_path)
    // 详情接口已经带 tags 了，兜底再查一次（老数据可能没有）
    if (Array.isArray(res.data.tags)) {
      questionTagIds.value = res.data.tags.map((t) => t.id)
    } else {
      await loadQuestionTags()
    }
  } catch (e) {
    // ⚠️ 课 32：统一用 parseError —— detail 可能是字符串、数组、或者压根没有
    errorMsg.value = parseError(e).message
  } finally {
    loading.value = false
  }
}

async function loadQuestionTags() {
  try {
    const res = await getQuestionTags(questionId.value)
    questionTagIds.value = (res.data.items || []).map((t) => t.id)
  } catch (e) {
    // ⚠️ 之前只 console.error → 标签区空着,老师以为没标签
    message.error(parseError(e).message)
  }
}

async function loadAllTags() {
  try {
    const res = await listTags()
    allTags.value = res.data.items || []
  } catch (e) {
    message.error(parseError(e).message)
  }
}

async function saveTags() {
  savingTags.value = true
  try {
    await setQuestionTags(questionId.value, questionTagIds.value)
    message.success('标签已保存')
    await load()
  } catch (e) {
    message.error(`保存失败：${e.response?.data?.detail || e.message}`)
  } finally {
    savingTags.value = false
  }
}

onMounted(() => {
  load()
  loadAllTags()
})

function onSaved() {
  editing.value = false
  load()
}

function doDelete() {
  dialog.warning({
    title: '删除这道题？',
    content: '删了就找不回来了。',
    positiveText: '确认删除',
    negativeText: '再想想',
    onPositiveClick: async () => {
      try {
        await deleteQuestion(questionId.value)
        router.replace({ name: 'questions' })
      } catch (e) {
        errorMsg.value = e.response?.data?.detail || '删除失败'
      }
    },
  })
}
</script>

<template>
  <div>
    <div class="tqb-page-head">
      <NButton size="small" quaternary @click="router.push({ name: 'questions' })">
        ← 返回题库
      </NButton>
      <NSpace v-if="question">
        <NButton size="small" @click="editing = true">编辑</NButton>
        <NButton size="small" type="error" @click="doDelete">删除</NButton>
      </NSpace>
    </div>

    <NAlert v-if="errorMsg" type="error" :bordered="false">{{ errorMsg }}</NAlert>

    <NSpin :show="loading">
      <NCard v-if="question" style="margin-top: 12px">
        <div class="tags">
          <NTag size="small" :bordered="false">{{ question.subject }}</NTag>
          <NTag size="small" :bordered="false">{{ question.question_type }}</NTag>
          <NTag size="small" :bordered="false">{{ question.grade }}</NTag>
          <NTag size="small" :bordered="false">{{ question.difficulty }}</NTag>
          <NTag
            v-for="t in question.tags || []"
            :key="t.id"
            size="small"
            :bordered="false"
            :color="{ color: (t.color || '#18a058') + '22', borderColor: t.color || '#18a058', textColor: t.color || '#18a058' }"
          >
            {{ t.name }}
          </NTag>
        </div>

        <!-- 标签编辑 -->
        <div class="tag-edit">
          <NSelect
            v-model:value="questionTagIds"
            :options="allTags.map((t) => ({ label: t.name, value: t.id }))"
            placeholder="选择标签"
            multiple
            filterable
            clearable
            size="small"
            style="max-width: 320px"
            @update:value="saveTags"
          />
          <NButton v-if="savingTags" size="small" loading disabled>保存中…</NButton>
        </div>

        <NDivider />

        <!-- 题干 + 题图（版式跟导出一致：右下角/右侧/下方居中/下方靠左/不显示） -->
        <div class="q-body" :class="figureLayoutClass">
          <!-- 题干(公式用 KaTeX 渲染) -->
          <div class="content" v-html="renderMathText(question.content_markdown || question.content_plain)" />

          <!-- 题图：OCR 从原图里裁出来的图形，随题保存、随题显示 -->
          <div v-if="question.figure_path && figureLayout !== 'none'" class="figure-box">
            <img
              v-if="figureBlobUrl"
              :src="figureBlobUrl"
              alt="题图"
              :style="figureImgStyle"
            />
            <NText v-else depth="3" style="font-size: 12px;">
              {{ figureFailed ? '题图加载失败' : '题图加载中…' }}
            </NText>
          </div>
        </div>

        <NDivider />

        <div class="meta">
          创建于 {{ new Date(question.created_at).toLocaleString('zh-CN') }}
        </div>
      </NCard>
    </NSpin>

    <!-- 编辑 -->
    <QuestionEditor
      v-if="editing && question"
      mode="edit"
      :question-id="question.id"
      :category-id="question.category_id"
      :plain-text="question.content_plain"
      :with-formulas="question.content_markdown"
      :blocks="question.blocks"
      :figure-path="question.figure_path || ''"
      :initial-figure-layout="question.figure_layout || 'bottom_right'"
      :initial-figure-width="question.figure_width || 0"
      :initial-subject="question.subject || ''"
      :initial-question-type="question.question_type || ''"
      :initial-grade="question.grade || ''"
      :initial-difficulty="question.difficulty || ''"
      @close="editing = false"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tag-edit {
  margin-top: 10px;
}

.content {
  font-size: 15px;
  line-height: 1.9;
}

/* === 题干 + 题图的排版（跟 PDF 导出同一套版式）=== */
.q-body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.q-body .content {
  flex: 1 1 auto;
  min-width: 0;
}
.q-body .figure-box {
  flex: 0 0 auto;
  max-width: 42%;
}
.q-bottom_right {
  align-items: flex-end;
}
.q-bottom_right .figure-box {
  max-width: 40%;
}
.q-right .figure-box {
  max-width: 34%;
}
.q-bottom_left,
.q-bottom_center {
  display: block;
}
.q-bottom_left .figure-box,
.q-bottom_center .figure-box {
  max-width: 60%;
  margin-top: 10px;
}
.q-bottom_center .figure-box {
  text-align: center;
}

.meta {
  font-size: 12px;
  color: #999;
}

.figure-box {
  margin-top: 12px;
}
</style>
