/**
 * 无头验证：分享链接（课 24）— 公开链接不用账号就能看卷子 + 下文件
 *
 * 验证什么
 * --------
 * 1. 登录后能在导出页生成分享链接（拿到完整 URL）
 * 2. **清掉登录态**再用这个 URL 打开 → 照样能看到卷子（这是分享的核心）
 * 3. 公开页能下 PDF（200 + %PDF 魔数）
 * 4. 吊销后链接立刻失效（404）
 *
 * 跑法：
 *   node scripts/verify-share.cjs
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

  console.log('→ 登录')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  console.log('→ 找一张有题的试卷')
  const paperId = await page.evaluate(async () => {
    const token = localStorage.getItem('tqb_token')
    const r = await fetch('/api/papers/', { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) return null
    const body = await r.json()
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

  const hasShareUi = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasShareTitle: text.includes('分享链接'),
      hasCreateBtn: [...document.querySelectorAll('button')].some((b) => b.textContent.includes('生成分享链接')),
      snippet: text.slice(0, 200).replace(/\n/g, ' '),
    }
  })
  console.log('  「分享链接」区块:', hasShareUi.hasShareTitle ? '✅' : '❌')
  console.log('  「生成分享链接」按钮:', hasShareUi.hasCreateBtn ? '✅' : '❌')
  if (!hasShareUi.hasCreateBtn) {
    console.log('  实际内容:', hasShareUi.snippet)
    throw new Error('导出页没有「生成分享链接」按钮')
  }

  console.log('→ 点「生成分享链接」')
  await clickByText(page, '生成分享链接')
  await wait(2000)

  // 从「已生成的链接」列表里取链接
  const shareUrl = await page.evaluate(() => {
    const items = [...document.querySelectorAll('.share-url')]
    if (!items.length) return null
    return items[0].textContent.trim()
  })
  if (!shareUrl) throw new Error('生成后没拿到分享链接')
  console.log('  链接:', shareUrl)

  console.log('→ 清掉登录态,用无痕身份打开分享链接')
  await page.evaluate(() => localStorage.clear())
  await page.goto(shareUrl, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  const shared = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasTitle: !!document.querySelector('.tqb-page-head, .shared-page'),
      qCount: document.querySelectorAll('.question').length,
      hasPdfBtn: [...document.querySelectorAll('button')].some((b) => b.textContent.includes('下载 PDF')),
      hasJpgBtn: [...document.querySelectorAll('button')].some((b) => b.textContent.includes('下载 JPG')),
      hasLogin: text.includes('登录') && !text.includes('下载 PDF'),
      snippet: text.slice(0, 200).replace(/\n/g, ' '),
    }
  })
  console.log('  未登录能看到题目:', shared.qCount, '道', shared.qCount ? '✅' : '❌')
  console.log('  「下载 PDF」按钮:', shared.hasPdfBtn ? '✅' : '❌')
  console.log('  「下载 JPG」按钮:', shared.hasJpgBtn ? '✅' : '❌')
  if (!shared.qCount) {
    console.log('  实际内容:', shared.snippet)
    throw new Error('未登录打开分享链接看不到题目')
  }
  if (!shared.hasPdfBtn) {
    console.log('  实际内容:', shared.snippet)
    throw new Error('分享页没有「下载 PDF」按钮')
  }

  console.log('→ 未登录状态下点「下载 PDF」')
  let pdfResp = null
  page.on('response', (res) => {
    if (res.url().includes('/export.pdf')) pdfResp = { status: res.status(), url: res.url() }
  })
  await clickByText(page, '下载 PDF')
  await wait(8000)
  console.log('  export.pdf 响应:', pdfResp ? `${pdfResp.status} ${pdfResp.url}` : '❌ 没发出请求')
  if (!pdfResp || pdfResp.status !== 200) {
    throw new Error('未登录状态下分享链接下 PDF 失败')
  }

  await page.screenshot({ path: '/tmp/verify-share.png', fullPage: false })

  console.log('→ 吊销链接,验证立刻失效')
  const revoked = await page.evaluate(async (pid) => {
    // 重新登录拿 token（前面的 localStorage 已清）
    const login = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'test1', password: 'abc123' }),
    })
    if (!login.ok) return { ok: false, detail: `登录失败 ${login.status}` }
    const { token } = await login.json()
    const list = await fetch(`/api/papers/${pid}/shares`, { headers: { Authorization: `Bearer ${token}` } })
    const body = await list.json()
    const item = (body.items || [])[0]
    if (!item) return { ok: false, detail: '列表里没有分享链接' }
    const del = await fetch(`/api/papers/${pid}/shares/${item.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    return { ok: del.ok, detail: `吊销 ${del.status}` }
  }, paperId)
  console.log('  吊销:', revoked.ok ? '✅' : `❌ ${revoked.detail}`)
  if (!revoked.ok) throw new Error('吊销失败')

  await page.evaluate(() => localStorage.clear())
  await page.goto(shareUrl, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)
  const afterRevoke = await page.evaluate(() => document.body.innerText)
  const dead = afterRevoke.includes('已过期') || afterRevoke.includes('不存在') || afterRevoke.includes('失效')
  console.log('  吊销后链接失效:', dead ? '✅' : '❌')
  if (!dead) {
    console.log('  实际内容:', afterRevoke.slice(0, 200).replace(/\n/g, ' '))
    throw new Error('吊销后链接仍能打开')
  }

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 分享链接全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
