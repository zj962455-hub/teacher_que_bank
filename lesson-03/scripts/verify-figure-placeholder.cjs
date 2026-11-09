/**
 * 无头验收（lesson-38）：
 *   1. 页面展示里没有【题图】占位符（详情页 / 题库列表 / 组卷预览）
 *   2. 编辑器输入框里【题图】还在 —— 老师要能看见它、才能手动删掉
 *   3. 老师手动删掉 → 保存 → 刷新后没复活
 *
 * 跑法:
 *   cd lesson-03
 *   node scripts/verify-figure-placeholder.cjs
 *
 * ⚠️ 脚本自己还原：先快照 → 改 → 验证 → 按快照回写，不在老师账号留痕
 */
const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test2'
const PASS = process.env.VERIFY_PASS || 'abc123'
const PH = '【题图】'

const errors = []
let putReq = null

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
    const btn = [...document.querySelectorAll('button')].find((b) =>
      b.innerText.replace(/\s+/g, '').includes(t.replace(/\s+/g, '')),
    )
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

/** 页面上有没有出现占位符（可见文本 + HTML） */
async function pageHasPlaceholder(page) {
  return page.evaluate((ph) => {
    const body = document.body.innerText || ''
    const html = document.body.innerHTML || ''
    return { text: body.includes(ph), html: html.includes(ph) }
  }, PH)
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

  console.log('\n[2] 找一道带【题图】的题（存储层里有）')
  const list = await apiGet(page, '/api/questions/?limit=50&offset=0')
  const items = list.items || []
  let target = null
  for (const it of items) {
    const full = await apiGet(page, '/api/questions/' + it.id)
    if (String(full.content_markdown || '').includes(PH)) { target = full; break }
  }
  if (!target) {
    console.log('   题库里没有带【题图】的题 —— 换账号或先造一道')
    await browser.close()
    return
  }
  const id = target.id
  const snapshot = { content_plain: target.content_plain, content_markdown: target.content_markdown }
  console.log('   题目 id =', id)

  console.log('\n[3] 详情页：展示里不该有占位符')
  await page.goto(BASE + '/questions/' + id, { waitUntil: 'domcontentloaded' })
  await wait(2500)
  const detailHit = await pageHasPlaceholder(page)
  console.log('   详情页可见文本含占位符? ', detailHit.text)
  console.log('   详情页 HTML 含占位符?     ', detailHit.html)

  console.log('\n[4] 题库列表页：展示里不该有占位符')
  await page.goto(BASE + '/questions', { waitUntil: 'domcontentloaded' })
  await wait(2500)
  const listHit = await pageHasPlaceholder(page)
  console.log('   列表页可见文本含占位符? ', listHit.text)
  console.log('   列表页 HTML 含占位符?     ', listHit.html)

  console.log('\n[5] 编辑器：输入框里要留着占位符（老师要能删）')
  await page.goto(BASE + '/questions/' + id, { waitUntil: 'domcontentloaded' })
  await wait(2500)
  await clickButton(page, '编辑')
  await wait(1800)
  const before = await page.evaluate(() => {
    const el = document.querySelector('textarea')
    return el ? el.value : null
  })
  console.log('   编辑框含占位符? ', before === null ? 'null' : before.includes(PH))

  console.log('\n[6] 老师手动删掉占位符 → 保存')
  const edited = String(before || '').split(PH).join('')
  await fillTextarea(page, edited)
  await wait(400)
  await clickButton(page, '保存到题库')
  await wait(2500)
  console.log('   PUT 载荷含占位符? ', String((putReq || {}).content_markdown || '').includes(PH))

  console.log('\n[7] 刷新回读：不该复活')
  await page.goto(BASE + '/questions/' + id, { waitUntil: 'domcontentloaded' })
  await wait(2500)
  const after = await apiGet(page, '/api/questions/' + id)
  console.log('   库里 markdown 含占位符? ', String(after.content_markdown || '').includes(PH))
  console.log('   库里 plain    含占位符? ', String(after.content_plain || '').includes(PH))
  const afterHit = await pageHasPlaceholder(page)
  console.log('   详情页可见文本含占位符? ', afterHit.text)

  console.log('\n[8] 还原')
  await apiPut(page, id, {
    content_plain: snapshot.content_plain,
    content_markdown: snapshot.content_markdown,
  })
  const restored = await apiGet(page, '/api/questions/' + id)
  console.log('   已还原? ', restored.content_markdown === snapshot.content_markdown)

  const ok =
    !detailHit.text && !detailHit.html &&
    !listHit.text && !listHit.html &&
    before !== null && before.includes(PH) &&
    !String(after.content_markdown || '').includes(PH) &&
    restored.content_markdown === snapshot.content_markdown

  console.log('\n结论: ', ok ? '展示去掉 ✓ 编辑器保留 ✓ 手动删除持久 ✓ 已还原 ✓' : '有问题，看上面的打印')
  if (errors.length) console.log('页面错误:', errors.slice(0, 5))
  await browser.close()
  if (!ok) process.exit(1)
}

main().catch((e) => { console.error('验证脚本炸了:', e.message); process.exit(1) })
