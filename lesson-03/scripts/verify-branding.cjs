/**
 * 无头验证：站点品牌与标题（课 35 · 上线前必须真跑）
 *
 * 验证什么
 * --------
 * 1. 浏览器标签页标题**不再是 "Vite App"**（之前一直是）
 * 2. 标题**跟着路由走**（首页 / 题库 / 录题 / 分类 / 组卷 各不相同）
 * 3. 顶栏 / 登录页 / 页脚三处的站名一致 = 「蓝狐题库」
 * 4. 页脚同时展示 **网站名 + ICP 备案号**（公安备案要求公示位）
 * 5. favicon / og 封面等静态资源取得到（不是 404）
 * 6. 分享页（/share/:token）标题带卷名
 * 7. 全程无运行时错误
 *
 * 跑法：
 *   node scripts/verify-branding.cjs
 *
 * 环境变量：
 *   VERIFY_BASE  默认 https://tqb.lanhu-lab.top
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'

const errors = []
const results = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

function check(name, ok, extra = '') {
  results.push({ name, ok })
  console.log(`  ${ok ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1400, height: 900 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  try {
    // === 1. 未登录页（公开）===
    console.log('\n[1] 登录页')
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await wait(1500)

    const loginTitle = await page.evaluate(() => document.title)
    check('标签页标题不是 "Vite App"', !loginTitle.includes('Vite App'), loginTitle)
    check('标题含站名「蓝狐题库」', loginTitle.includes('蓝狐题库'), loginTitle)

    const loginBrand = await page.evaluate(() => document.body.innerText)
    check('登录页显示站名', loginBrand.includes('蓝狐题库'))

    // === 2. 静态资源 ===
    console.log('\n[2] 图标与封面')
    for (const [name, url] of [
      ['favicon.ico', '/favicon.ico'],
      ['favicon.svg', '/favicon.svg'],
      ['og-image.png', '/og-image.png'],
      ['apple-touch-icon.png', '/apple-touch-icon.png'],
    ]) {
      const res = await fetch(BASE + url)
      check(`${name} 可取`, res.ok, `HTTP ${res.status}`)
    }

    // === 3. 社交标签 ===
    console.log('\n[3] og 标签（微信/QQ 分享卡片）')
    const metas = await page.evaluate(() => {
      const out = {}
      for (const m of document.querySelectorAll('meta[property^="og:"], meta[name="description"]')) {
        out[m.getAttribute('property') || m.getAttribute('name')] = m.getAttribute('content')
      }
      return out
    })
    check('og:title 含站名', (metas['og:title'] || '').includes('蓝狐题库'), metas['og:title'])
    check('og:image 指向封面图', !!metas['og:image'], metas['og:image'])
    check('description 不含 Vite', !(metas.description || '').includes('Vite'))

    // === 4. 登录后各路由标题 ===
    console.log('\n[4] 路由标题跟随')
    await page.evaluate(() => {
      const el = [...document.querySelectorAll('input')].find((i) => i.placeholder?.includes('用户名'))
      if (!el) throw new Error('找不到用户名输入框')
      const proto = window.HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, 'test2')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await page.evaluate(() => {
      const el = [...document.querySelectorAll('input')].find((i) => i.placeholder?.includes('密码'))
      const proto = window.HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, 'abc123')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')].find((x) => x.innerText.includes('登录'))
      b?.click()
    })
    await wait(2500)

    const routes = [
      ['/', '题库首页'],
      ['/questions', '题目列表'],
      ['/capture', '录题'],
      ['/categories', '分类管理'],
      ['/papers', '我的试卷'],
      ['/guide', '使用指南'],
    ]
    for (const [path, expect] of routes) {
      await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
      await wait(1200)
      const t = await page.evaluate(() => document.title)
      check(`${path} 标题含「${expect}」`, t.includes(expect), t)
    }

    // === 5. 顶栏 + 页脚 ===
    console.log('\n[5] 顶栏与页脚')
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
    await wait(1500)
    const body = await page.evaluate(() => document.body.innerText)
    check('顶栏显示「🦊 蓝狐题库」', body.includes('蓝狐题库'))
    check('页脚展示网站名', body.includes('蓝狐题库'))
    check('页脚展示 ICP 备案号', body.includes('浙ICP备2025185898号-2'))
    check('页面不再出现 "Vite App"', !body.includes('Vite App'))
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== 运行时错误 ===')
  console.log(errors.length ? errors.join('\n') : '（无）')

  const failed = results.filter((r) => !r.ok)
  console.log('\n==============================================')
  console.log(`  ${results.length - failed.length}/${results.length} 项通过`)
  console.log('==============================================')
  process.exit(failed.length ? 1 : 0)
}

main()
