/**
 * API 地址配置 — lesson-10 部署改造
 *
 * 为什么要有这个文件
 * ------------------
 * 之前各处都硬编码 `http://localhost:8000`：
 *   - 本地开发能用
 *   - 部署到 ECS 后浏览器访问的是 `tqb.lanhu-lab.top`，
 *     里面的 localhost 指向**老师自己的电脑** → 直接挂
 *
 * 改法：统一从这里取，开发/生产各用一份 env 文件
 *
 * 环境变量
 * --------
 * | 文件 | VITE_API_BASE | 场景 |
 * |---|---|---|
 * | .env.development | http://localhost:8000 | 本地 vite dev |
 * | .env.production  | （空 → /api）| 部署后，同源反代 |
 *
 * 生产为什么用相对路径
 * ------------------
 * 部署架构是**同源**：
 *   https://tqb.lanhu-lab.top/       → nginx 托管 Vue dist
 *   https://tqb.lanhu-lab.top/api/   → nginx 反代 127.0.0.1:8000
 * 用相对路径 /api 就不用管域名，也不会撞 CORS。
 */

/**
 * 后端根地址（不含 /api）
 *
 * ⚠️ 必须用 ?? 不能用 ||
 * --------------------------------
 * .env.production 里写的是 `VITE_API_BASE=`（空值），
 * Vite 解析成**空字符串** ''。
 *
 * '' 是 falsy → 用 || 会 fallback 到 'http://localhost:8000'
 *    → 生产构建产物里带着 localhost → 部署后浏览器访问自己电脑 → 直接挂
 *
 * ?? 只在 null / undefined 时 fallback，空字符串会原样保留。
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** API 根地址（含 /api） */
export const API = `${API_BASE}/api`

export default { API_BASE, API }
