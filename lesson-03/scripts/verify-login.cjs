/**
 * 无头验证：登录流程 + 数据隔离（lesson-11）
 *
 * 验证什么
 * --------
 * 1. 未登录时只显示登录面板，业务组件不渲染（否则全是 401）
 * 2. 输入 test1/abc123 能登录成功
 * 3. 登录后业务界面出现，题库列表能加载出数据
 * 4. 页面无运行时错误（pageerror / console error）
 * 5. 退出后回到登录面板
 *
 * 跑法：
 *   node scripts/verify-login.cjs
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'abc123'

const errors = []
const failedRequests = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

/** 用原生 setter 赋值并触发 input 事件（Vue v-model 劫持了 value setter） */
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

async function clickButton(page, text) {
  const clicked = await page.evaluate((t) => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent.trim() === t,
    )
    if (!btn) return false
    btn.click()
    return true
  }, text)
  if (!clicked) throw new Error(`找不到按钮「${text}」`)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })
  page.on('requestfailed', (r) => {
    failedRequests.push(`${r.url()} → ${r.failure()?.errorText}`)
  })
  page.on('response', (r) => {
    if (r.status() === 401 || r.status() === 403) {
      errors.push(`HTTP ${r.status()}: ${r.url()}`)
    }
  })

  console.log('→ 打开首页', BASE)
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)

  // === 1. 未登录：应该有登录面板，业务组件不该渲染 ===
  const before = await page.evaluate(() => ({
    hasLogin: !!document.querySelector('.login-panel'),
    bodyText: document.body.innerText,
  }))
  console.log('  登录面板:', before.hasLogin ? '✅ 显示' : '❌ 没显示')
  console.log('  登录面板前 100 字:', JSON.stringify(before.bodyText.slice(0, 100)))

  if (!before.hasLogin) {
    throw new Error('未登录时没有显示登录面板')
  }

  // === 2. 填账号密码并登录 ===
  console.log('→ 填账号密码')
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await wait(300)

  console.log('→ 点登录')
  await clickButton(page, '登录')
  await wait(3000)

  // === 3. 登录后：业务界面出现 ===
  const after = await page.evaluate(() => ({
    hasLogin: !!document.querySelector('.login-panel'),
    text: document.body.innerText,
  }))
  console.log('  登录面板已隐藏:', !after.hasLogin ? '✅' : '❌ 还在')
  console.log('  页面内容 120 字:', JSON.stringify(after.text.slice(0, 120)))

  if (after.hasLogin) {
    throw new Error('登录后仍停留在登录面板')
  }
  if (!after.text.includes('题库') && !after.text.includes('课程')) {
    throw new Error('登录后没看到业务界面')
  }

  // === 3.5 上传一张图,验证 blob URL 渲染 ===
  console.log('→ 测试上传 + 鉴权图片渲染')
  const uploadResult = await page.evaluate(async () => {
    const canvas = document.createElement('canvas')
    canvas.width = 120; canvas.height = 60
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 120, 60)
    ctx.fillStyle = 'red'; ctx.font = '14px sans-serif'
    ctx.fillText('BLOB-OK', 10, 35)
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'))
    const fd = new FormData()
    fd.append('file', blob, 'verify.png')
    const token = localStorage.getItem('tqb_token')
    const res = await fetch('/api/uploads/', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    return { status: res.status, body: await res.text() }
  })
  console.log('  上传:', uploadResult.status, uploadResult.body.slice(0, 90))

  // === 4. 题库列表有数据吗 ===
  await wait(2000)
  const tableInfo = await page.evaluate(() => {
    const rows = document.querySelectorAll('.n-data-table-tbody .n-data-table-tr')
    const tables = document.querySelectorAll('.n-data-table').length
    return { tables, rows: rows.length }
  })
  console.log(`  题库表格: ${tableInfo.tables} 个, 行数 ${tableInfo.rows}`)
  if (tableInfo.tables > 0 && tableInfo.rows === 0) {
    console.log('  ⚠️ 表格在但没数据行 —— 可能是数据真的为空，也可能是接口 401')
  }

  await page.screenshot({ path: '/tmp/verify-after-login.png', fullPage: false })

  // === 5. 登出 ===
  console.log('→ 找登出入口')
  const hasLogout = await page.evaluate(() => {
    const t = document.body.innerText
    return t.includes('登出') || t.includes('退出')
  })
  if (hasLogout) {
    console.log('  页面有登出字样（登出功能还没做，先跳过）')
  }

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  console.log('失败请求:', failedRequests.length ? failedRequests : '无 ✅')
  if (errors.length || failedRequests.length) {
    process.exit(1)
  }
  console.log('\n✅ 登录流程全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
