import { createDiscreteApi } from 'naive-ui'

/**
 * 全局 toast 实例（离散 API）
 * ---------------------------------
 * 为什么不用 useMessage()
 * -----------------------
 * useMessage() 必须在 <NMessageProvider> 内部调用。
 * OcrBlockList / QuestionEditor 这类组件会被复用到不同层级，
 * 如果哪天用在 Provider 之外，useMessage() 会拿到 undefined → 运行时白屏。
 *
 * createDiscreteApi 创建的是**独立实例**，不依赖组件树层级，
 * 任何文件 import 就能用：
 *
 *   import { message } from '@/composables/discreteApi'
 *   message.success('已复制')
 *
 * ⚠️ 参数签名（2026-10-22 白屏事故的教训）
 * ---------------------------------------
 * createDiscreteApi(apis: string[], config?)
 *                  ↑ 第一参数是「要创建哪些 API」的名称数组
 *
 * 我第一版错误地传了 config 对象：
 *   createDiscreteApi({ configProviderProps: {...} })   ← ❌ 报 includes.forEach is not a function
 *
 * 报错在 naive-ui 内部，看栈很难定位，所以记在这里。
 * 正确用法见 NaiveUIDemo.vue:180（本项目已有先例）。
 */
export const { message, dialog, notification, loadingBar } = createDiscreteApi([
  'message',
  'dialog',
  'notification',
  'loadingBar',
])