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
 *   回填公安备案号：bash deploy/teacher-bank/fill-mps-number.sh <备案号>
 *   主体名称 / 应急联系方式：
 *     bash deploy/teacher-bank/fill-mps-number.sh --operator "<主办单位全称>" --contact "<对外联系方式>"
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

// 公安备案号 —— **还没拿到**（2026-11-19 安全部门审核中）。
// 拿到后用 fill-mps-number.sh 回填（它会改这个文件并部署）。
// 空字符串 = 页脚整块不渲染，隐私政策里也不出现这一行（不显示半截空号）。
export const MPS = ''

// 公安备案查询链接：只放备案号里的**数字**部分
// （公安官网自己的示例就是 ?code=11010102000001，显示文字才是全称）
export const MPS_QUERY = 'https://beian.mps.gov.cn/#/query/webSearch?code='
// ⚠️ 这里必须是**单个**反斜杠。若写成 /\\d{6,}/，正则会去匹配「反斜杠 + d」，
//    结果 MPS_CODE 恒为空 → 公安查询链接变成 ?code=（废链接，审核点开是 404）。
//    2026-11-19 实测发现，已修。
export const MPS_CODE = (MPS.match(/\d{6,}/) || [''])[0]

// === 主体信息 ===
// ⚠️ 这两项在隐私政策页**公开展示**，所以按「最小必要」填：
//    · 主体：填**与公安备案提交材料一致**的主体名称
//      （企业站 = 营业执照全称；个人站 = 备案登记的姓名/名称，不要写「个人运营」这种泛称，
//        审核会核对「页面显示的名字」与备案是否一致）
//    · 联系方式：优先填**专用邮箱**；不建议填私人手机号 ——
//      手机号会被爬虫抓走变成推销/诈骗来电的来源，也会和账号体系里的手机号混淆。
// ⚠️ **身份证号、证件照片、家庭住址、银行卡一律不进这个文件** ——
//    它们只出现在提交给主管部门的备案材料里，**不在网站上公开**。
//
// 🔒 **真实值走 .env.local，不进 git**（2026-11-20 改）：
//    这个仓库是 **public** 的，而本文件是入库文件 —— 把姓名和邮箱写在这里，
//    等于把个人信息推到公开仓库里，删掉也还能从 git 历史里翻出来。
//    改成从环境变量读：
//      frontend/.env.local        ← 真实值（.gitignore 已忽略，不入库）
//      frontend/.env.development  ← 空值占位（入库，安全）
//      frontend/.env.production   ← 空值占位（入库，安全）
//    构建时由 Vite 注入 → 产物里有值 → 线上正常显示；
//    本地没填 → 值为空字符串 → 页面上这一行**直接不出现**
//    （而不是显示半成品文字：审核员看到会当成备案材料没填，负分）。
export const OPERATOR = import.meta.env.VITE_OPERATOR || ''
export const CONTACT = import.meta.env.VITE_CONTACT || ''

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
