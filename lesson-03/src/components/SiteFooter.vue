<script setup>
// 页脚 · ICP 备案号
// 2026-11-02: 公安联网备案要求网站展示备案号，与工信部 ICP 备案一并公示
const ICP = "浙ICP备2025185898号-2"
const MIIT = "https://beian.miit.gov.cn/"
</script>

<template>
  <footer class="site-footer">
    <a :href="MIIT" target="_blank" rel="noopener noreferrer" class="beian">
      {{ ICP }}
    </a>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: 32px;
  padding: 18px 0 24px;
  border-top: 1px solid #e6e6e6;
  text-align: center;
  font-size: 12px;
  line-height: 1.6;
}

.beian {
  color: #8c8c8c;
  text-decoration: none;
  transition: color 0.2s;
}

.beian:hover {
  color: #595959;
}
</style>
