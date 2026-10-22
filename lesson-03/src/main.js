import { createApp } from 'vue'
import App from './App.vue'

/**
 * 为什么不用 <NMessageProvider>
 * -----------------------------
 * naive-ui 的 message/toast 有两种用法：
 *
 * 1. <NMessageProvider> 包裹根组件 + useMessage()
 *    - Provider 必须写在 template 里，不能用 app.use()
 *    - app.use() 只能接「插件」（有 install 方法的对象）
 *    - NMessageProvider 是「组件」不是「插件」→ .use() 会静默失效 → useMessage() 拿到 undefined → 运行时白屏
 *    - 我第一版就踩了这个坑（2026-10-22 22:19 白屏事故）
 *
 * 2. createDiscreteApi() 创建独立实例
 *    - 不需要 Provider 包裹，任意文件 import 就能用
 *    - OcrBlockList / OcrResult / QuestionEditor 这些组件不用关心 Provider 层级
 *
 * 本项目选方案 2 —— 组件复用多，方案 1 会让每个组件都依赖 Provider 存在。
 * 实例定义见 src/composables/discreteApi.js
 */
createApp(App).mount('#app')