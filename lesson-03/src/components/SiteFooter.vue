<script setup>
// 页脚 · 网站名 + ICP 备案号 + 公安备案号（备案要求公示位）
//
// 三个号/名的分工
// ---------------
// - 网站名「蓝狐题库」：公安备案填的「网站名称」，跟工信部 ICP 备案那条
//   （浙ICP备2025185898号-2）保持一致 —— 审核时会核对「页面显示的名字」
//   与备案信息是否相符，所以这里显式写出来，不只是写一个数字。
// - ICP 备案号：工信部要求首页底部展示，并链到工信部查询页。
// - 公安备案号：还没拿到（截止 2026-12-02），拿到后加在同一行。
const SITE_NAME = '蓝狐题库'
const ICP = '浙ICP备2025185898号-2'
const MIIT = 'https://beian.miit.gov.cn/'

// 公安备案号（待老大提交后拿到号回填）
const MPS = '' // 例：浙公网安备XXXXXXXXXXXXXX号
</script>

<template>
  <footer class="site-footer">
    <div class="site-footer-row">
      <span class="site-name">{{ SITE_NAME }}</span>
      <a :href="MIIT" target="_blank" rel="noopener noreferrer" class="beian">
        {{ ICP }}
      </a>
      <a
        v-if="MPS"
        href="https://beian.mps.gov.cn/#/query/webSearch?code={{ MPS }}"
        target="_blank"
        rel="noopener noreferrer"
        class="beian"
      >
        {{ MPS }}
      </a>
    </div>
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

.site-footer-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.site-name {
  color: #595959;
  font-weight: 500;
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
