/**
 * 站点信息 —— 全站唯一来源（lesson-43 · 公安备案）
 *
 * 为什么收口到这里
 * ----------------
 * 备案相关的字段以前散在两个文件里：
 *   - SiteFooter.vue 的 ICP / MPS 常量
 *   - PrivacyPage.vue 的 OPERATOR / CONTACT 常量
 *
 * 备案是一个**里程碑事件**：拿到公安备案号、拿到主体名称与联系方式，
 * 都要改页面。而公安审核会核对「页面显示的名字」与备案是否一致 ——
 * 漏改一处就是不一致。
 *
 * 所以：**备案要改的字段，全放这一个文件**。
 * 回填公安备案号用一条命令：
 *   bash deploy/teacher-bank/fill-mps-number.sh <备案号>
 *
 * ⚠️ 这里的字段都会**公开展示在网站上**（备案要求公示），不是密钥。
 *    私密信息（密码、AK）一律不进这个文件。
 */

// === 站点标识 ===
// 公安备案填的「网站名称」，与工信部 ICP 备案那条
// （浙ICP备2025185898号-2）登记的网站名称必须完全一致
export const SITE_NAME = '蓝狐网'

// 主域名
export const SITE_DOMAIN = 'tqb.lanhu-lab.top'

// === 备案公示号 ===

// 工信部 ICP 备案号（已取得，页脚公示）
export const ICP = '浙ICP备2025185898号-2'

// 公安备案号 —— **还没拿到**（截止 2026-12-02）。
// 拿到后用 fill-mps-number.sh 回填（它会改这个文件并部署）。
// 空字符串 = 页脚整块不渲染（不显示半截空号）。
export const MPS = ''

// 公安备案查询链接：只放备案号里的**数字**部分
// （公安官网自己的示例就是 ?code=11010102000001，显示文字才是全称）
export const MPS_QUERY = 'https://beian.mps.gov.cn/#/query/webSearch?code='
export const MPS_CODE = (MPS.match(/\d{6,}/) || [''])[0]

// === 主体信息 ===
// ⚠️ 这两项在 PrivacyPage 公开展示，**必须与营业执照、备案提交材料完全一致**。
//    现在还是占位 —— 备案提交前必须由主办单位填成真实信息。
export const OPERATOR = '（待填 —— 主办单位名称，须与营业执照一致）'
export const CONTACT = '（待填 —— 备案要求填写的应急联系电话 / 邮箱）'

export default {
  SITE_NAME,
  SITE_DOMAIN,
  ICP,
  MPS,
  MPS_CODE,
  MPS_QUERY,
  OPERATOR,
  CONTACT,
}
