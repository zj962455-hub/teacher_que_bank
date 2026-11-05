/**
 * 无头验证：试卷导出页（JPG 导出）— lesson-23
 *
 * 验证什么
 * --------
 * 1. 试卷导出页能打开，且显示试卷内容（题号 + 题干）
 * 2. 「导出 JPG」按钮存在
 * 3. 点它 → 真的发出 /api/papers/{id}/export.jpg 且返回 200
 * 4. 全程无运行时错误（pageerror / console.error）
 *
 * 跑法：
 *   node scripts/verify-export-jpg.cjs
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'abc123'

const errors = []

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
  if (!ok) throw new Error(`找不到「${text}」`)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1600, height: 1000 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  // 记录 export.jpg 的响应
  let jpgResp = null
  page.on('response', (res) => {
    if (res.url().includes('/export.jpg')) jpgResp = { status: res.status(), url: res.url() }
  })

  console.log('→ 登录')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  // 拿一张有题的卷
  console.log('→ 找一张有题的试卷')
  const paperId = await page.evaluate(async () => {
    const token = localStorage.getItem('tqb_token')
    const r = await fetch('/api/papers/', { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) return null
    const body = await r.json()
    // 线上返回的是分页结构 {items, total},不是裸数组
    const list = Array.isArray(body) ? body : body.items || []
    for (const p of list) {
      const d = await fetch(`/api/papers/${p.id}`, { headers: { Authorization: `Bearer ${token}` } })
      if (d.ok) {
        const detail = await d.json()
        if (detail.questions && detail.questions.length) return p.id
      }
    }
    return null
  })
  if (!paperId) throw new Error('线上没有有题目的试卷,无法验证')
  console.log('  用 paper_id =', paperId)

  console.log('→ 打开导出页')
  await page.goto(`${BASE}/papers/${paperId}/export`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  const view = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasTitle: text.includes('导出'),
      hasJpgBtn: [...document.querySelectorAll('button')].some((b) => b.textContent.includes('导出 JPG')),
      hasPdfBtn: [...document.querySelectorAll('button')].some((b) => b.textContent.includes('导出 PDF')),
      hasQuestion: !!document.querySelector('.question'),
      qCount: document.querySelectorAll('.question').length,
      snippet: text.slice(0, 160).replace(/\n/g, ' '),
    }
  })

  console.log('  页面含「导出」:', view.hasTitle ? '✅' : '❌')
  console.log('  「导出 PDF」按钮:', view.hasPdfBtn ? '✅' : '❌')
  console.log('  「导出 JPG」按钮:', view.hasJpgBtn ? '✅' : '❌')
  console.log('  题目渲染:', view.qCount, '道', view.hasQuestion ? '✅' : '❌')

  if (!view.hasJpgBtn) {
    console.log('  实际内容:', view.snippet)
    throw new Error('没有「导出 JPG」按钮')
  }
  if (!view.qCount) {
    console.log('  实际内容:', view.snippet)
    throw new Error('导出页没渲染题目')
  }

  console.log('→ 点「导出 JPG」')
  await clickByText(page, '导出 JPG')
  await wait(6000)

  console.log('  export.jpg 响应:', jpgResp ? `${jpgResp.status} ${jpgResp.url}` : '❌ 没发出请求')
  if (!jpgResp || jpgResp.status !== 200) {
    throw new Error('导出 JPG 请求没成功')
  }

  await page.screenshot({ path: '/tmp/verify-export-jpg.png', fullPage: false })
  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 试卷导出页（JPG）全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
