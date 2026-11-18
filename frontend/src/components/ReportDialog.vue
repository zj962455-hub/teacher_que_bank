<script setup>
/**
 * ReportDialog — 举报弹窗（公开举报入口）— lesson-43
 *
 * 为什么放在分享页上
 * ------------------
 * 官方第（六）项要「公开举报、举报方式等信息举报渠道的畅通」。
 * 平台唯一对外暴露内容的页面就是公开分享页 —— 访客在这里看到有害内容，
 * 想举报时手边就得有这个入口。放到需要登录的后台，等于把渠道堵死。
 *
 * 不要求登录
 * ----------
 * 访客没有账号。强制登录就等于「渠道不畅通」。登录了就顺手记下是谁
 * （后端有 reporter_user_id），没登录就匿名报（可留联系方式）。
 *
 * 举报人怎么知道结果
 * ------------------
 * 提交后返回**受理编号**，页面直接展示并提示保存 —— 凭编号可随时查进展。
 */
import { ref, computed } from 'vue'
import {
  NModal, NCard, NForm, NFormItem, NSelect, NInput, NButton, NSpace,
  NAlert, NDivider, NText,
} from 'naive-ui'
import { submitReport, REASONS, TARGET_TYPES } from '../api/reports'
import { parseError } from '../utils/errors'

const props = defineProps({
  show: { type: Boolean, default: false },
  // 被举报对象
  targetType: { type: String, default: 'other' },
  targetId: { type: [Number, String], default: null },
  targetDesc: { type: String, default: '' },
})
const emit = defineEmits(['update:show', 'done'])

const submitting = ref(false)
const errorMsg = ref('')
const result = ref(null)

const form = ref({
  reason: 'illegal',
  detail: '',
  reporter_name: '',
  reporter_contact: '',
})

const reasonOptions = REASONS
const targetOptions = TARGET_TYPES

const canSubmit = computed(() => form.value.detail.trim().length >= 5)

async function doSubmit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    const res = await submitReport({
      target_type: props.targetType,
      target_id: props.targetId ? Number(props.targetId) : null,
      target_desc: props.targetDesc,
      reason: form.value.reason,
      detail: form.value.detail,
      reporter_name: form.value.reporter_name,
      reporter_contact: form.value.reporter_contact,
    })
    result.value = res.data
    emit('done', res.data)
  } catch (e) {
    errorMsg.value = parseError(e, '举报提交失败')
  } finally {
    submitting.value = false
  }
}

function close() {
  errorMsg.value = ''
  result.value = null
  form.value = { reason: 'illegal', detail: '', reporter_name: '', reporter_contact: '' }
  emit('update:show', false)
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    style="max-width: 560px"
    title="举报违法有害信息"
    :mask-closable="!submitting"
    @update:show="(v) => { if (!v) close() }"
  >
    <!-- 提交成功：展示受理编号 -->
    <template v-if="result">
      <NAlert type="success" :bordered="false">
        举报已受理。请保存下方**受理编号**，凭编号可查询处理进展。
      </NAlert>
      <NDivider style="margin: 14px 0" />
      <NText depth="3">受理编号</NText>
      <div class="report-no">{{ result.report_no }}</div>
      <NSpace style="margin-top: 16px">
        <NButton type="primary" @click="close">知道了</NButton>
      </NSpace>
    </template>

    <template v-else>
      <NAlert v-if="errorMsg" type="error" :bordered="false" style="margin-bottom: 12px">
        {{ errorMsg }}
      </NAlert>

      <NForm label-placement="top">
        <NFormItem label="举报对象">
          <NSelect :value="targetType" :options="targetOptions" disabled />
        </NFormItem>
        <NFormItem v-if="targetDesc" label="对象说明">
          <NText depth="3">{{ targetDesc }}</NText>
        </NFormItem>
        <NFormItem label="举报类型">
          <NSelect v-model:value="form.reason" :options="reasonOptions" />
        </NFormItem>
        <NFormItem label="举报说明">
          <NInput
            v-model:value="form.detail"
            type="textarea"
            :rows="4"
            placeholder="请说明具体问题（至少 5 个字）"
            maxlength="1000"
            show-count
          />
        </NFormItem>
        <NFormItem label="您的称呼（选填）">
          <NInput v-model:value="form.reporter_name" placeholder="便于回访，可留空" maxlength="50" />
        </NFormItem>
        <NFormItem label="联系方式（选填）">
          <NInput v-model:value="form.reporter_contact" placeholder="手机号或邮箱，可留空" maxlength="100" />
        </NFormItem>
      </NForm>

      <NSpace justify="end">
        <NButton :disabled="submitting" @click="close">取消</NButton>
        <NButton type="primary" :disabled="!canSubmit" :loading="submitting" @click="doSubmit">
          提交举报
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.report-no {
  margin-top: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
}
</style>
