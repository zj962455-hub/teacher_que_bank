import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [
    vue(),
    // ⚠️ 课 33 性能：devtools **只在 dev 模式挂**。
    //    之前无条件挂载 → 生产包里混进了 devtools 客户端代码
    //    （实测同一个 chunk 从 277 KB 缩到 138 KB）。
    //    线上没人用 devtools，纯属白下。
    ...(command === 'serve' ? [vueDevTools()] : []),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // ⚠️ **不要**在这里写 manualChunks
    //    —— 试过把 vue / katex 手动拆成独立 chunk，
    //    结果 rolldown 把一堆依赖卷进去，首屏 JS 从 555 KB 涨到 1002 KB。
    //    rollup 自己的分包（按动态 import 边界）已经够好：
    //    katex 只在渲染公式的页面被动态 import 时才下。
    chunkSizeWarningLimit: 800,
  },
}))
