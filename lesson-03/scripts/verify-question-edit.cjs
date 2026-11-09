
/**
 * 无头验收（lesson-37）：
 *   1. 详情页「编辑 → 保存到题库」真的落库（改的字能读回来）
 *   2. 题图排版下拉只有三个选项：文字下方右下 / 文字下方左下 / 不显示
 *
 * 跑法:
 *   cd lesson-03
 *   node scripts/verify-question-edit.cjs
 */
const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test2'
const PASS = process.env.VERIFY_PASS || 'abc123'
const MARK = '【验收标记-改完会还原】'

const errors = []
let putReq = null
let putResp = null

async function wait(ms) { return new Promise((r) => setTimeout(r, ms)) }

async function fillTextarea(page, value) {
  await page.evaluate((val) => {
    const el = document.querySelector('textarea')
    if (!el) throw new Error('找不到 textarea')
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    setter.call(el, val)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, value)
}

async function clickButton(page, text) {
  const ok = await page.evaluate((t) => {
    const btn = [...document.querySelectorAll('button')].find((b) => b.innerText.replace(/\s+/g, '').includes(t.replace(/\s+/g, '')))
    if (!btn) return false
    btn.click()
    return true
  }, text)
  if (!ok) throw new Error('找不到按钮「' + text + '」')
}

async function apiGet(page, path) {
  return page.evaluate(async (p) => {
    const t = localStorage.getItem('tqb_token')
    const r = await fetch(p, { headers: { Authorization: 'Bearer ' + t } })
    return await r.json()
  }, path)
}

async function apiPut(page, id, payload) {
  return page.evaluate(async (i, p) => {
    const t = localStorage.getItem('tqb_token')
    const r = await fetch('/api/questions/' + i, {
      method: 'PUT',
      headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' },
      body: JSON.stringify(p),
    })
    return { status: r.status, body: await r.json() }
  }, id, payload)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1400, height: 950 })

  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()) })
  page.on('request', (req) => {
    if (req.method() === 'PUT' && req.url().includes('/api/questions/')) {
      try { putReq = JSON.parse(req.postData() || 'null') } catch (e) { putReq = req.postData() }
    }
  })
  page.on('response', async (r) => {
    if (r.request().method() === 'PUT' && r.url().includes('/api/questions/')) {
      try { putResp = { status: r.status(), body: await r.json() } } catch (e) { putResp = { status: r.status() } }
    }
  })

  console.log('\n[1] 登录')
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
  await wait(1500)
  await page.evaluate((u, p) => {
    const set = (ph, val) => {
      const el = [...document.querySelectorAll('input')].find((i) => i.placeholder && i.placeholder.includes(ph))
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, val)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    set('用户名', u); set('密码', p)
  }, USER, PASS)
  await clickButton(page, '登录')
  await wait(2500)
  console.log('   url =', page.url())

  console.log('\n[2] 取第一道题做快照')
  const list = await apiGet(page, '/api/questions/?limit=5&offset=0')
  const item = (list.items || [])[0]
  if (!item) throw new Error('题库是空的，没法验')
  const id = item.id
  const snapshot = await apiGet(page, '/api/questions/' + id)
  console.log('   题目 id =', id, '| markdown 长度 =', (snapshot.content_markdown || '').length)

  console.log('\n[3] 详情页 → 编辑')
  await page.goto(BASE + '/questions/' + id, { waitUntil: 'domcontentloaded' })
  await wait(2500)
  await clickButton(page, '编辑')
  await wait(1500)
  const before = await page.evaluate(() => {
    const el = document.querySelector('textarea')
    return el ? el.value : null
  })
  console.log('   编辑框内容长度 =', before === null ? 'null' : before.length)

  console.log('\n[3.5] 题图排版下拉')
  const opened = await page.evaluate(() => {
    const spans = [...document.querySelectorAll('span, div')].filter(
      (e) => e.children.length === 0 && e.textContent.trim() === '题图排版',
    )
    if (!spans.length) return false
    const holder = spans[0].closest('.n-space') || spans[0].parentElement
    const sel = holder ? holder.querySelector('.n-base-selection') : null
    if (!sel) return false
    sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    sel.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    sel.click()
    return true
  })
  if (opened) {
    await wait(1200)
    const optTexts = await page.evaluate(() =>
      [...document.querySelectorAll('.n-base-select-option')].map((o) => o.innerText.trim()).filter(Boolean),
    )
    console.log('   下拉选项 =', JSON.stringify(optTexts))
    await page.keyboard.press('Escape')
    await wait(600)
  } else {
    console.log('   （这题没图或没渲染排版下拉，跳过）')
  }

  console.log('\n[4] 改文字并保存')
  const edited = (before || '') + '\n' + MARK
  await fillTextarea(page, edited)
  await wait(400)
  await clickButton(page, '保存到题库')
  await wait(2500)

  console.log('\n[5] 看实际发出去的 PUT 载荷')
  console.log('   请求体含验收标记? ', String((putReq || {}).content_markdown || '').includes(MARK))
  console.log('   PUT 响应状态 =', putResp ? putResp.status : '没抓到')
  if (putResp && putResp.body && putResp.body.content_markdown) {
    console.log('   响应里的 markdown 含标记? ', String(putResp.body.content_markdown).includes(MARK))
  }

  console.log('\n[6] 刷新详情页回读')
  await page.goto(BASE + '/questions/' + id, { waitUntil: 'domcontentloaded' })
  await wait(2500)
  const after = await apiGet(page, '/api/questions/' + id)
  const persisted = String(after.content_markdown || '').includes(MARK)
  console.log('   库里含验收标记? ', persisted)
  console.log('   纯文本版也跟着改了? ', !String(after.content_plain || '').includes('原题内容'))

  console.log('\n[7] 还原内容')
  await apiPut(page, id, {
    content_plain: snapshot.content_plain,
    content_markdown: snapshot.content_markdown,
  })
  const restored = await apiGet(page, '/api/questions/' + id)
  console.log('   已还原? ', restored.content_markdown === snapshot.content_markdown)

  console.log('\n结论: ', persisted ? '保存生效' : '保存没落库')
  if (errors.length) console.log('页面错误:', errors.slice(0, 5))
  await browser.close()
}

main().catch((e) => { console.error('验证脚本炸了:', e.message); process.exit(1) })
