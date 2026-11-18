/**
 * useAsyncTask — 统一的异步任务状态管理（课 32）
 *
 * 解决什么
 * --------
 * 每个页面都在写同一套样板：
 *
 *   const loading = ref(false)
 *   const errorMsg = ref('')
 *   async function load() {
 *     loading.value = true
 *     errorMsg.value = ''
 *     try {
 *       const res = await listPapers()
 *       data.value = res.data
 *     } catch (e) {
 *       errorMsg.value = e.response?.data?.detail || `加载失败：${e.message}`
 *     } finally {
 *       loading.value = false
 *     }
 *   }
 *
 * 问题有三个：
 * 1. **错误文案各写一遍** —— 网络错误时全都显示成「失败：Network Error」，老师看不懂
 * 2. **按钮不知道在忙** —— 提交后没有 loading 反馈 → 重复点击 → 重复提交
 * 3. **失败后没法重试** —— 只能刷新整页
 *
 * 这个 composable 把三件事收成一处：
 * - ``run()`` —— 执行任务，自动管 loading / 错误
 * - ``retry()`` —— 失败后原地重试（用上次的参数）
 * - ``loading`` —— 按钮据此 disable，杜绝重复提交
 *
 * 用法
 * ----
 * ```js
 * const { data, loading, error, run, retry } = useAsyncTask(listPapers)
 * onMounted(() => run())
 * ```
 * 模板里：
 * ```html
 * <NSpin :show="loading">
 *   <div v-if="error">
 *     <NAlert type="error">{{ error.message }}</NAlert>
 *     <NButton @click="retry">重试</NButton>
 *   </div>
 *   <div v-else>…</div>
 * </NSpin>
 * ```
 */

import { ref, shallowRef } from 'vue'
import { parseError } from '../utils/errors'

/**
 * @param {Function} task - 返回 Promise 的函数
 * @param {Object} options
 * @param {Function} options.onSuccess - 成功回调（可选）
 * @param {Function} options.onError - 失败回调（可选）
 * @param {boolean} options.silent - 失败时不设 error（用于「后台刷新」这种不打断用户的场景）
 */
export function useAsyncTask(task, options = {}) {
  const { onSuccess, onError, silent = false } = options

  const data = shallowRef(null)
  const loading = ref(false)
  const error = ref(null)

  // 记住上次的参数 —— retry 要用
  let lastArgs = []

  /**
   * 执行任务
   * @param {...any} args - 透传给 task
   * @returns {Promise<any>} 成功返回值；失败抛 ApiError
   */
  async function run(...args) {
    // ⚠️ 已经在跑就不重复发起 —— 老师连点两下「保存」，
    //    第二个请求会把第一条覆盖掉（PUT 是全量更新）。
    if (loading.value) return undefined

    lastArgs = args
    loading.value = true
    if (!silent) error.value = null

    try {
      const result = await task(...args)
      data.value = result
      if (onSuccess) onSuccess(result)
      return result
    } catch (e) {
      const parsed = parseError(e)
      if (!silent) error.value = parsed
      if (onError) onError(parsed)
      throw parsed
    } finally {
      loading.value = false
    }
  }

  /** 失败后原地重试（用上次的参数） */
  function retry() {
    return run(...lastArgs).catch(() => undefined)
  }

  /** 手动清掉错误（比如用户改了输入，不该再显示旧的报错） */
  function clearError() {
    error.value = null
  }

  return { data, loading, error, run, retry, clearError }
}

export default useAsyncTask
