<script setup>
/**
 * TaskState — 统一的「加载中 / 出错了 / 空」三态渲染（课 32）
 *
 * 为什么要有这个组件
 * ------------------
 * 每个页面都要处理三件事：
 * - 加载中 → 转圈（NSpin）
 * - 出错了 → 红条 + 一句人话 + 「重试」按钮
 * - 空数据 → 提示 + 一个引导动作
 *
 * 之前是每页各写一遍，写法还不一样：有的页面出错只 ``console.error``，
 * 老师看到的是**一片空白**，连「服务器炸了」都不知道。
 *
 * 用法
 * ----
 * ```html
 * <TaskState :loading="loading" :error="error" :empty="!items.length" @retry="retry">
 *   <template #empty>
 *     <NEmpty description="还没有题目">
 *       <NButton type="primary" @click="router.push({name:'capture'})">去录题</NButton>
 *     </NEmpty>
 *   </template>
 *   <div v-for="q in items" :key="q.id">…</div>
 * </TaskState>
 * ```
 */
import { NSpin, NAlert, NButton, NEmpty, NSpace } from 'naive-ui'

defineProps({
  /** 正在加载 */
  loading: { type: Boolean, default: false },
  /** 错误对象（ApiError）—— 有值就显示错误块 */
  error: { type: Object, default: null },
  /** 是否为空 */
  empty: { type: Boolean, default: false },
  /** 空状态文案 */
  emptyText: { type: String, default: '还没有内容' },
})

const emit = defineEmits(['retry'])
</script>

<template>
  <div class="task-state">
    <!-- 出错了：错误优先于一切（数据可能是上一次的旧值，不能显示） -->
    <template v-if="error">
      <NAlert type="error" :bordered="false">
        <div class="err-text">{{ error.message }}</div>
        <NSpace style="margin-top: 8px" align="center">
          <NButton size="small" @click="emit('retry')">重试</NButton>
          <!-- request_id 是排查用的：老师截图报错时它在界面上，
               运维拿这个 id 直接搜服务端日志 -->
          <span v-if="error.request_id" class="err-rid">
            错误编号 {{ error.request_id }}
          </span>
        </NSpace>
      </NAlert>
    </template>

    <!-- 加载中 -->
    <NSpin v-else-if="loading" :show="true" description="加载中…" class="spin-wrap">
      <div class="spin-slot"><slot /></div>
    </NSpin>

    <!-- 空 -->
    <template v-else-if="empty">
      <slot name="empty">
        <NEmpty :description="emptyText" />
      </slot>
    </template>

    <!-- 正常 -->
    <template v-else>
      <slot />
    </template>
  </div>
</template>

<style scoped>
.task-state {
  min-height: 120px;
}

.spin-wrap {
  display: block;
  width: 100%;
}

/* 加载时把内容藏起来，但保留高度 —— 避免加载完页面高度突变，晃眼 */
.spin-slot {
  opacity: 0.35;
  min-height: 120px;
}

.err-text {
  font-size: 14px;
  line-height: 1.6;
}

.err-rid {
  font-size: 11px;
  color: var(--tqb-text-tertiary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
