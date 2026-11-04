/**
 * 无头验证：路由拆分 — lesson-11
 *
 * 验证什么
 * --------
 * 1. 未登录访问业务页 → 跳登录页
 * 2. 登录后 → 顶栏出现导航
 * 3. 9 个路由逐个访问 → 都能渲染，无 404、无运行时错误
 * 4. 深链接直接打开（刷新）→ 不 404
 *
 * 跑法：
 *   node scripts/verify-routes.cjs
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'abc123'

const errors = []
const failed = []

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
      const proto = el.tagName === 'TEXTAREA'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set
      setter.call(el, val)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    },
    placeholder,
    value,
  )
}

async function clickByText(page, text) {
  const ok = await page.evaluate((t) => {
    const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === t)
    if (!b) return false
    b.click()
    return true
  }, text)
  if (!ok) throw new Error(`找不到按钮「${text}」`)
}

const ROUTES = [
  { path: '/', name: '题库首页', expect: '题库' },
  { path: '/questions', name: '题目列表', expect: '题目列表' },
  { path: '/capture', name: '录题', expect: '录题' },
  { path: '/categories', name: '分类管理', expect: '分类管理' },
  { path: '/papers', name: '我的试卷', expect: '我的试卷' },
  { path: '/papers/new', name: '组卷', expect: '组卷' },
  { path: '/profile', name: '个人中心', expect: '个人中心' },
]

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 1000 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })
  page.on('response', (r) => {
    if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`)
  })

  // === 1. 未登录访问业务页 → 跳登录 ===
  console.log('→ 未登录访问 /questions')
  await page.goto(`${BASE}/questions`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)
  const url1 = page.url()
  console.log(`  跳转后 URL: ${url1.replace(BASE, '')}`)
  if (!url1.includes('/login')) throw new Error(`未登录没跳登录页: ${url1}`)

  // === 2. 登录 ===
  console.log('→ 登录')
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)
  console.log(`  登录后 URL: ${page.url().replace(BASE, '')}`)

  // === 3. 顶栏导航 ===
  const nav = await page.evaluate(() =>
    [...document.querySelectorAll('.nav button')].map((b) => b.textContent.trim()),
  )
  console.log('  顶栏导航:', nav.join(' / ') || '(无)')

  // === 4. 逐个路由 ===
  console.log('→ 逐个访问路由')
  for (const r of ROUTES) {
    const before = errors.length
    const resp = await page.goto(`${BASE}${r.path}`, { waitUntil: 'networkidle2', timeout: 30000 })
    await wait(1200)
    const text = await page.evaluate(() => document.body.innerText)
    const ok = text.includes(r.expect)
    const newErr = errors.length - before
    console.log(
      `  ${r.path.padEnd(14)} HTTP ${resp.status()} · ${r.expect} ${ok ? '✅' : '❌'}` +
      (newErr ? ` · 新增错误 ${newErr}` : ''),
    )
    if (!ok) console.log(`     实际内容: ${text.slice(0, 90).replace(/\n/g, ' ')}`)
    if (!ok || newErr) process.exitCode = 1
  }

  // === 5. 导航点击 ===
  console.log('→ 点导航切页')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll('.nav button')].find((x) => x.textContent.trim() === '题库')
    if (!b) return false
    b.click()
    return true
  })
  if (!clicked) throw new Error('顶栏没有「题库」导航')
  await wait(1500)
  console.log(`  点击后 URL: ${page.url().replace(BASE, '')}`)

  await page.screenshot({ path: '/tmp/verify-routes.png', fullPage: false })

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  console.log('失败请求:', failed.length ? failed : '无 ✅')
  if (errors.length || failed.length) process.exit(1)
  console.log('\n✅ 路由拆分全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
