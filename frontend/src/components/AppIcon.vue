# 统一图标组件 —— 替换散落各处的 emoji
#
# 为什么要有这一层
# --------------
# 之前界面上的图标全是 emoji（🦊 📚 📤 📂 ⏳ …）：
#   - 字体不同平台渲染不同，字重/基线对不齐
#   - 描边粗细不统一，和旁边的文字放一起很脏
#   - 深色模式、灰度打印下几乎不可控
# 现在统一成一套 24×24 线性 SVG：currentColor 描边（1.6px），
# 颜色跟着文字走，hover/选中态只改 color，不用换图。
<script setup>
/**
 * AppIcon — 统一线性图标（24×24，currentColor 描边）
 *
 * 用法：<AppIcon name="upload" :size="16" />
 * 说明：markup 全部是本文件里的静态常量，不是用户输入 —— v-html 安全。
 */
defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
})

const ICONS = {
  fox: '<path d="M4.5 4.2 8.6 7h6.8l4.1-2.8v5.4c0 6.2-3.7 9.8-7.5 10.9-3.8-1.1-7.5-4.7-7.5-10.9z"/><path d="M9.2 11.6h.01M14.8 11.6h.01"/>',
  home: '<path d="M3.5 10.4 12 3.6l8.5 6.8V19a1.4 1.4 0 0 1-1.4 1.4h-4.2v-6H9.1v6H4.9A1.4 1.4 0 0 1 3.5 19z"/>',
  stack: '<path d="M4.5 5.5h6a2 2 0 0 1 2 2v11a1.5 1.5 0 0 0-1.5-1.5h-6.5z"/><path d="M19.5 5.5h-6a2 2 0 0 0-2 2v11a1.5 1.5 0 0 1 1.5-1.5h6.5z"/>',
  scan: '<path d="M3.5 9.5A1.5 1.5 0 0 1 5 8h2.3a1 1 0 0 0 .8-.4l1-1.3a1 1 0 0 1 .8-.4h4.2a1 1 0 0 1 .8.4l1 1.3a1 1 0 0 0 .8.4H19a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M15.5 13a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0z"/>',
  folder: '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2.5h8a1.5 1.5 0 0 1 1.5 1.5v7.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/>',
  file: '<path d="M6.5 3.5h7l4.5 4.5v12.5h-11.5z"/><path d="M13.5 3.5V8H18"/>',
  message: '<path d="M4 5.5h16v10.5H9.5L4.5 19.5V16H4z"/>',
  book: '<path d="M4 5a1.5 1.5 0 0 1 1.5-1.5H11V21H5.5A1.5 1.5 0 0 1 4 19.5z"/><path d="M11 3.5h7.5A1.5 1.5 0 0 1 20 5v14.5a1.5 1.5 0 0 1-1.5 1.5H11"/>',
  ticket: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h13A1.5 1.5 0 0 1 20 8.5v1.8a1.7 1.7 0 0 0 0 3.4v1.8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 15.5v-1.8a1.7 1.7 0 0 0 0-3.4z"/><path d="M10 7v2M10 11v2M10 15v2"/>',
  shield: '<path d="M12 3.2 19 6v6.2c0 4.4-2.9 7.4-7 8.8-4.1-1.4-7-4.4-7-8.8V6z"/><path d="M12 8.6v4"/><path d="M12 15.6h.01"/>',
  user: '<path d="M12 12.2a4.1 4.1 0 1 0 0-8.2 4.1 4.1 0 0 0 0 8.2z"/><path d="M4.6 20.2a7.4 7.4 0 0 1 14.8 0"/>',
  sun: '<path d="M12 16.4a4.4 4.4 0 1 0 0-8.8 4.4 4.4 0 0 0 0 8.8z"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4 7 7M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6"/>',
  moon: '<path d="M20 14.6A8.6 8.6 0 0 1 9.4 4 8.6 8.6 0 1 0 20 14.6z"/>',
  upload: '<path d="M12 16V4.5M12 4.5 7.8 8.7M12 4.5l4.2 4.2"/><path d="M4 15.5v3A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
  image: '<path d="M4.5 4.5h15v15h-15z"/><path d="M4.5 16l4.5-4.5 3.5 3.5 3-3 4 4"/><path d="M15.5 9.2h.01"/>',
  search: '<path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z"/><path d="M16.2 16.2 20.5 20.5"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v4.5h-4.5"/>',
  trash: '<path d="M4.5 7h15"/><path d="M9.5 7V4.8h5V7"/><path d="M6.8 7l.9 12.2a1.4 1.4 0 0 0 1.4 1.3h5.8a1.4 1.4 0 0 0 1.4-1.3L17.2 7"/>',
  download: '<path d="M12 4v11.5M12 15.5 8 11.5M12 15.5l4-4"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>',
  plus: '<path d="M12 5.5v13M5.5 12h13"/>',
  clock: '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M12 7v5.2l3.2 2"/>',
  edit: '<path d="M4.5 19.5h4l10-10a2.1 2.1 0 0 0-3-3l-10 10z"/><path d="M13.5 6.5l3 3"/>',
  chart: '<path d="M4 20h16"/><path d="M7 20v-9M12 20V6M17 20v-6"/>',
  filter: '<path d="M4 5.5h16l-6.2 7.3v5.4l-3.6 1.8v-7.2z"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/>',
  copy: '<path d="M9 9h9.5A1.5 1.5 0 0 1 20 10.5V20a1.5 1.5 0 0 1-1.5 1.5H9A1.5 1.5 0 0 1 7.5 20v-9.5A1.5 1.5 0 0 1 9 9z"/><path d="M15 6.5V5A1.5 1.5 0 0 0 13.5 3.5H5A1.5 1.5 0 0 0 3.5 5v8.5A1.5 1.5 0 0 0 5 15h1.5"/>',
  save: '<path d="M5 4.5h10.5L19.5 8.5V18a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18V6A1.5 1.5 0 0 1 5 4.5z"/><path d="M7.5 4.5v5h7v-5"/><path d="M7.5 19.5v-5h9v5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  robot: '<path d="M12 3.5v2M7.5 6.5h9A2.5 2.5 0 0 1 19 9v6a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 15V9a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M9.5 11h.01M14.5 11h.01M10 14.5h4"/>',
  tag: '<path d="M4 11.5V5.5A1.5 1.5 0 0 1 5.5 4h6l8 8-8 8z"/><path d="M8.5 8.5h.01"/>',
  link: '<path d="M10 13.5a3.5 3.5 0 0 0 5 0l3-3a3.54 3.54 0 0 0-5-5l-1.5 1.5"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.54 3.54 0 0 0 5 5l1.5-1.5"/>',
  grid: '<path d="M4 4.5h6.5V11H4zM13.5 4.5H20V11h-6.5zM4 13h6.5v6.5H4zM13.5 13H20v6.5h-6.5z"/>',
}
</script>

<template>
  <svg
    class="app-icon"
    :width="$props.size"
    :height="$props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="ICONS[$props.name] || ''"
  />
</template>

<style scoped>
.app-icon {
  flex-shrink: 0;
  display: block;
}
</style>
