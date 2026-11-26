<script setup>
// 页脚 · 网站名 + ICP 备案号 + 公安备案号（备案要求公示位）
//
// 这些字段**不在本文件定义** —— 统一在 src/site.config.js（备案里程碑要改的都在那儿）。
//
// 三个号/名的分工
// --------------
// - 网站名「蓝狐网」：公安备案填的「网站名称」，跟工信部 ICP 备案那条
//   （浙ICP备2025185898号-2）保持一致 —— 审核时会核对「页面显示的名字」
//   与备案信息是否相符，所以这里显式写出来，不只是写一个数字。
// - ICP 备案号：工信部要求首页底部展示，并链到工信部查询页。
// - 公安备案号：还没拿到（2026-11-20 仍在审核、尚未下发；原定截止 2026-12-02），拿到后回填 site.config.js 的 MPS。
//
// ⚠️ 公安备案号的链接**必须用 :href 绑定**
// ------------------------------------
// 写成静态 href="...{{ MPS }}" 的话，Vue 的 {{ }} 插值在属性里不生效 ——
// 会原样输出成字面量 ?code={{ MPS }}，链接就废了。
// （2026-11-18 修过一次这个坑，并加进 test_frontend_sanity.py 防复发）
//
// ⚠️ 链接的 code 参数**只放数字**，显示文字才放全称
// ----------------------------------------------
// 公安官网自己的页面里硬编码的示例是
//   https://beian.mps.gov.cn/#/query/webSearch?code=11010102000001
// 显示文字则是「京公网安备11010102000001号」。
// 也就是 code = 备案记录号（数字），不是「浙公网安备…号」那串全称。
// 所以下面从全称里自动摘出数字，只填一处就够，不用填两遍。
//
// ⚠️ 公安备案图标**必须本地托管**，不能外链
// ------------------------------------
// 官方老路径 https://beian.mps.gov.cn/img/gh.png 已失效（2026-11-18 实测）：
// 返回的是官网 SPA 的 index.html（content-type: text/html，749 字节），
// 浏览器会把它当 HTML 解析 → 图标位置变成一片空白或裂图。
// 现在用的是官网自己的真图 logo01.dd7ff50e.png（金色公安徽章，62×67 PNG），
// 已经下载到 frontend/public/gh-beian.png 本地托管 —— 对方改版也不会裂。
// 链接仍然指向官方查询页，图标本身本地提供。
//
// 备案要求不只是写号码，还要带**图标**并链到公安网安局查询页 ——
// 图标用官方提供的那张，alt 写中文「公安备案图标」。
import { SITE_NAME, ICP, MPS, MPS_CODE, MPS_QUERY } from '../site.config'
const MIIT = 'https://beian.miit.gov.cn/'



// 公安备案图标 —— 官方徽章，已下载到 frontend/public/ 本地托管（不外链，见上方说明）
const MPS_ICON = '/gh-beian.png'

// 举报与投诉入口（违法和不良信息举报 / 公安网络违法犯罪举报）
// —— 公安备案「违法有害信息举报受理渠道」这一项要有个能点的地方
const REPORT_12377 = 'https://www.12377.cn/'
const REPORT_POLICE = 'https://cyberpolice.mps.gov.cn'
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
        :href="MPS_QUERY + MPS_CODE"
        target="_blank"
        rel="noopener noreferrer"
        class="beian mps"
      >
        <img :src="MPS_ICON" alt="公安备案图标" class="mps-icon" />
        {{ MPS }}
      </a>
    </div>

    <div class="site-footer-row site-footer-report">
      <span class="report-label">举报与投诉：</span>
      <a :href="REPORT_12377" target="_blank" rel="noopener noreferrer" class="beian">
        违法和不良信息举报中心（12377）
      </a>
      <span class="report-sep">·</span>
      <a :href="REPORT_POLICE" target="_blank" rel="noopener noreferrer" class="beian">
        公安网络违法犯罪举报网站
      </a>
      <span class="report-sep">·</span>
      <a href="/privacy" class="beian">隐私政策与用户协议</a>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: 32px;
  padding: 18px 0 24px;
  /* 页脚要有自己的底色：否则备案号小字实际落在页底色上，
     三级文字只有 4.47:1，压线不过 AA（白卡上是 4.83） */
  background: var(--tqb-bg-card);
  border-top: 1px solid var(--tqb-border);
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
  color: var(--tqb-text-secondary);
  font-weight: 500;
}

.beian {
  color: var(--tqb-text-secondary);
  text-decoration: none;
  transition: color 0.2s;
}

.beian:hover {
  color: var(--tqb-text-secondary);
}

/* 举报入口 —— 与备案号同一区域，灰一点不抢视觉 */
.site-footer-report {
  margin-top: 6px;
  font-size: 12px;
}

.report-label {
  color: var(--tqb-text-secondary);
}

.report-sep {
  color: var(--tqb-border-strong);
}

/* 公安备案图标 —— 官方规定要带图标并可点击跳查询页 */
.mps {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.mps-icon {
  width: 16px;
  height: 16px;
  display: block;
}
</style>
