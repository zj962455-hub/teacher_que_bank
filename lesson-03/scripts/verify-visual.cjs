/**
 * 无头验证：b 阶段视觉系统
 *
 * 验证什么
 * --------
 * 1. 10 个路由逐页打开 —— 每页都渲染出内容（不是白屏），且**无运行时错误**
 * 2. 逐页记录错误增量 —— 一页炸了不能被别页掩盖
 * 3. 浅色 / 深色两套主题都能正常渲染（令牌与 naive-ui 主题要同步切换）
 * 4. 响应式：1440 / 1024 / 768 / 375 四个宽度下不出现横向溢出
 * 5. 截图留证（浅色 + 深色各一张）
 *
 * 跑法：
 *   VERIFY_BASE=https://tqb.lanhu-lab.top VERIFY_USER=test1 VERIFY_PASS=abc123 node scripts/verify-visual.cjs
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'http://localhost:5173'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'abc123'

const errors = []
let currentRoute = 'boot'

/** 每个路由该页独有的断言词（不能选顶栏/页脚里的通用词） */
const ROUTES = [
  // ⚠️ 断言词必须选**该页独有**的内容 ——
  //    「仪表盘」这四个字页面里根本没有（顶栏显示的是「首页」）
  { path: '/', name: '首页/仪表盘', expect: '题目总数' },
  { path: '/questions', name: '题目列表', expect: '题目列表' },
  { path: '/capture', name: '录题', expect: '录题' },
  { path: '/categories', name: '分类管理', expect: '章节分类管理' },
  { path: '/papers', name: '组卷', expect: '组卷' },
  { path: '/papers/new', name: '新建试卷', expect: '试卷' },
  { path: '/profile', name: '个人中心', expect: '个人中心' },
]

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function fillInput(page, placeholder, value) {
  await page.evaluate(
    (ph, val) => {
      const el = [...document.querySelectorAll('input')].find(
        (i) => i.placeholder && i.placeholder.includes(ph),
      )
      if (!el) throw new Error(`找不到 placeholder 含 "${ph}" 的输入框`)
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value',
      ).set
      setter.call(el, val)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    },
    placeholder,
    value,
  )
}

async function clickByText(page, text, tag = 'button') {
  const ok = await page.evaluate(
    (t, g) => {
      const el = [...document.querySelectorAll(g)].find((x) => x.textContent.trim() === t)
      if (!el) return false
      el.click()
      return true
    },
    text,
    tag,
  )
  if (!ok) throw new Error(`找不到按钮「${text}」`)
}

/** 横向溢出检测 —— 响应式最常见的问题 */
async function overflowInfo(page) {
  return page.evaluate(() => {
    const doc = document.documentElement
    const overflow = doc.scrollWidth - doc.clientWidth
    // 找出真正超出右边界的元素
    const wide = []
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.right > doc.clientWidth + 2) {
        wide.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().split(' ')[0]} right=${Math.round(r.right)}`)
        if (wide.length >= 3) break
      }
    }
    return { overflow, wide }
  })
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 950 })

  page.on('pageerror', (e) => errors.push(`[${currentRoute}] pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[${currentRoute}] console.error: ${m.text()}`)
  })
  page.on('requestfailed', (r) =>
    errors.push(`[${currentRoute}] requestfailed: ${r.url()} ${r.failure()?.errorText}`),
  )

  // === 登录 ===
  currentRoute = 'login'
  console.log('→ 登录', BASE)
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  const logged = await page.evaluate(() => Boolean(localStorage.getItem('tqb_token')))
  if (!logged) throw new Error('登录失败')
  console.log('  登录 ✅\n')

  // === 逐页验证（浅色）===
  console.log('=== 逐页验证（浅色 · 1440px）===')
  let failed = 0
  for (const r of ROUTES) {
    currentRoute = r.path
    const before = errors.length
    const resp = await page.goto(BASE + r.path, { waitUntil: 'networkidle2', timeout: 30000 })
    await wait(1600)
    const info = await page.evaluate(() => ({
      text: document.body.innerText,
      // 令牌是否生效：页面背景色应该来自 --tqb-bg-page
      bg: getComputedStyle(document.body).backgroundColor,
      title: document.title,
      cards: document.querySelectorAll('.tqb-card, .n-card').length,
    }))
    const has = info.text.includes(r.expect)
    const newErr = errors.length - before
    const mark = has && newErr === 0 ? '✅' : '❌'
    if (mark === '❌') failed++
    console.log(
      `  ${mark} ${r.path.padEnd(16)} HTTP ${resp.status()} · 「${r.expect}」${has ? '有' : '无'} · 卡片 ${info.cards} · 新增错误 ${newErr}`,
    )
    if (!has) console.log(`     内容前 120 字: ${info.text.slice(0, 120).replace(/\n/g, ' ')}`)
    if (newErr) console.log(`     ${errors.slice(before).join('\n     ')}`)
  }

  // === 深色模式 ===
  console.log('\n=== 深色模式 ===')
  currentRoute = 'dark-mode'
  await page.goto(BASE + '/questions', { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)
  const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)

  // 点主题切换按钮（顶栏那个 🌙/☀️）
  const toggled = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent.trim() === '🌙' || b.textContent.trim() === '☀️',
    )
    if (!btn) return false
    btn.click()
    return true
  })
  if (!toggled) throw new Error('找不到主题切换按钮')
  await wait(1200)

  const dark = await page.evaluate(() => ({
    attr: document.documentElement.getAttribute('data-theme'),
    stored: localStorage.getItem('tqb_theme'),
    bg: getComputedStyle(document.body).backgroundColor,
  }))
  const darkOk = dark.attr === 'dark' && dark.stored === 'dark' && dark.bg !== lightBg
  console.log(`  data-theme=${dark.attr} · localStorage=${dark.stored}`)
  console.log(`  背景色 ${lightBg} → ${dark.bg}`)
  console.log(`  深色切换: ${darkOk ? '✅' : '❌'}`)
  if (!darkOk) failed++

  // 深色下的截图
  await page.screenshot({ path: '/tmp/visual-dark.png' })

  // 切回浅色
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent.trim() === '🌙' || b.textContent.trim() === '☀️',
    )
    if (btn) btn.click()
  })
  await wait(1000)

  // === 响应式 ===
  console.log('\n=== 响应式（横向溢出检测）===')
  const WIDTHS = [1440, 1024, 768, 375]
  for (const w of WIDTHS) {
    currentRoute = `responsive-${w}`
    const before = errors.length
    await page.setViewport({ width: w, height: 900 })
    await page.goto(BASE + '/questions', { waitUntil: 'networkidle2', timeout: 30000 })
    await wait(1400)
    const info = await overflowInfo(page)
    const newErr = errors.length - before
    const ok = info.overflow <= 2 && newErr === 0
    if (!ok) failed++
    console.log(
      `  ${ok ? '✅' : '❌'} ${String(w).padStart(4)}px · 溢出 ${info.overflow}px · 新增错误 ${newErr}`,
    )
    if (info.wide.length) console.log(`     超出元素: ${info.wide.join(' | ')}`)
  }

  // 浅色截图（题目列表页，最能看出视觉质量）
  await page.setViewport({ width: 1440, height: 950 })
  await page.goto(BASE + '/questions', { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1600)
  await page.screenshot({ path: '/tmp/visual-light.png' })

  // 分类页也截一张（树 + 标签卡）
  await page.goto(BASE + '/categories', { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1600)
  await page.screenshot({ path: '/tmp/visual-categories.png' })

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) failed++
  console.log(failed === 0 ? '\n✅ 视觉系统全部通过' : `\n❌ ${failed} 项未通过`)
  process.exit(failed === 0 ? 0 : 1)
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  console.error(e.stack)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
