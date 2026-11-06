<script setup>
/**
 * FeedbackModal — 反馈弹窗 — lesson-34
 *
 * 干什么
 * ------
 * 顶栏点「反馈」弹出来：选类别 + 写两句 → 提交。
 *
 * 为什么做成弹窗而不是独立页面
 * ----------------------------
 * 反馈是「想起来就写一句」的动作 —— 老师正在用着某个功能，
 * 发现点不动，随手写两句。让他跳去另一个页面再写，**大部分人会放弃**。
 *
 * 自动带页面路径
 * ------------
 * 提交时把当前路由（``route.fullPath``）一起发上去 ——
 * 管理员看到「在哪一页出的问题」才能复现，光看「导出坏了」是猜不出来的。
 *
 * 「谁提的」
 * --------
 * 灰度阶段几个老师**共用一个账号** → 只看账号分不出是谁提的。
 * 所以多一个「你的名字 / 身份」输入框，**默认值取当前账号的显示名** ——
 * 老师改一下就行，不用从零填。
 *
 * 异步状态
 * --------
 * 走 useAsyncTask（课 32）：提交中按钮 loading（防重复提交），
 * 失败显示后端的人话文案（parseError）。
 */
import { ref, computed } from 'vue'
import {
  NModal, NCard, NRadioGroup, NRadioButton, NInput, NButton, NSpace, NText, NAlert,
} from 'naive-ui'
import { useRoute } from 'vue-router'
import { submitFeedback, CATEGORIES } from '../api/feedback'
import { getCachedUser } from '../api/auth'
import { message } from '../composables/discreteApi'
import { useAsyncTask } from '../composables/useAsyncTask'

const props = defineProps({
  show: { type: Boolean, default: false },
})
const emit = defineEmits(['update:show', 'submitted'])

const route = useRoute()

const category = ref('bug')
const content = ref('')
const hint = ref('')

// 「谁提的」—— 默认取当前账号的显示名（老师改一下就行）
const reporter = ref(getCachedUser()?.display_name || getCachedUser()?.username || '')
const contact = ref('')

const { loading, error, run, clearError } = useAsyncTask(
  async () => {
    return submitFeedback({
      category: category.value,
      content: content.value.trim(),
      page_url: route.fullPath || '/',
      reporter: reporter.value.trim(),
      contact: contact.value.trim(),
    })
  },
  {
    onSuccess: () => {
      message.success('反馈已提交，谢谢！')
      content.value = ''
      // ⚠️ reporter / contact 不清空 —— 同一个老师可能要连着提好几句，
      //    每次重填身份太烦。
      emit('submitted')
      emit('update:show', false)
    },
  },
)

// 当前页面（提交时一起发上去，管理员好复现）
const pagePath = computed(() => route.fullPath || '/')

function close() {
  if (loading.value) return
  hint.value = ''
  clearError()
  emit('update:show', false)
}

async function handleSubmit() {
  hint.value = ''
  clearError()
  const text = content.value.trim()
  if (text.length < 5) {
    hint.value = '再多写几个字吧（至少 5 个字）'
    return
  }
  if (!reporter.value.trim()) {
    hint.value = '写一下你的名字或身份（方便管理员回复你）'
    return
  }
  try {
    await run()
  } catch {
    // 错误已在 error.message 里（后端给的中文：内容太短/太长等）
  }
}
</script>

<template>
  <NModal :show="show" @update:show="close">
    <NCard title="💬 提个意见" style="max-width: 520px" :bordered="false" role="dialog">
      <NAlert v-if="hint || error" type="error" :bordered="false" style="margin-bottom: 12px">
        {{ hint || error?.message }}
      </NAlert>

      <div class="fb-label">这是什么问题？</div>
      <NRadioGroup v-model:value="category" :disabled="loading" class="fb-cats">
        <NRadioButton v-for="c in CATEGORIES" :key="c.value" :value="c.value">
          {{ c.label }}
        </NRadioButton>
      </NRadioGroup>

      <div class="fb-label">你是哪位老师？</div>
      <NInput
        v-model:value="reporter"
        placeholder="例如：张老师·市三中"
        :maxlength="50"
        :disabled="loading"
      />

      <div class="fb-label">联系方式（选填）</div>
      <NInput
        v-model:value="contact"
        placeholder="微信 / 手机，方便管理员回你（可以不填）"
        :maxlength="100"
        :disabled="loading"
      />

      <div class="fb-label">说具体点</div>
      <NInput
        v-model:value="content"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :maxlength="2000"
        show-count
        placeholder="例如：导出 PDF 时，根号变成了方块。哪个页面、点了哪里也写上。"
        :disabled="loading"
      />

      <NText depth="3" style="font-size: 12px; display: block; margin-top: 8px">
        会附带当前页面路径：{{ pagePath }}（方便定位问题）
      </NText>

      <template #footer>
        <NSpace justify="end">
          <NButton :disabled="loading" @click="close">取消</NButton>
          <NButton type="primary" :loading="loading" @click="handleSubmit">
            提交反馈
          </NButton>
        </NSpace>
      </template>
    </NCard>
  </NModal>
</template>

<style scoped>
.fb-label {
  font-size: 13px;
  color: var(--tqb-text-secondary);
  margin: 4px 0 6px;
}

.fb-cats {
  margin-bottom: 14px;
}

/* 两个新输入框（姓名 / 联系方式）之间留点气 */
.fb-label + .n-input,
.fb-label + .n-radio-group {
  margin-bottom: 12px;
}
</style>
