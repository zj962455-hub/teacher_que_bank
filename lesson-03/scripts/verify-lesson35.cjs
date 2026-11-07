/**
 * lesson-35 端到端验收
 * 一次上传那张「同时踩中三个坑」的题图：
 *   1) 公式里混中文 → KaTeX 吐红字
 *   2) 平行符号 PE/OA
 *   3) 填空横线丢失 + 图形不显示
 */
const puppeteer = require('puppeteer-core')
const fs = require('fs')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = 'https://tqb.lanhu-lab.top'
const USER = 'test2'
const PASS = 'abc123'
const IMG = '/Users/rrobot/.openclaw/workspace/tmp-verify2/20261108_004950_d8b6b398.png'
const SHOT_DIR = '/Users/rrobot/.openclaw/workspace/tmp-verify2'

async function wait(ms) { return new Promise((r) => setTimeout(r, ms)) }

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1100 })
  page.on('console', (m) => {
    const t = m.text()
    if (/error|Error|fail/i.test(t)) console.log('  [browser console]', t.slice(0, 200))
  })

  // ---- 登录 ----
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
  await wait(1500)
  await page.evaluate((u, p) => {
    const set = (ph, v) => {
      const el = [...document.querySelectorAll('input')].find((i) => i.placeholder && i.placeholder.includes(ph))
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    set('用户名', u); set('密码', p)
    ;[...document.querySelectorAll('button')].find((b) => b.innerText.includes('登录')).click()
  }, USER, PASS)
  await wait(3000)
  console.log('登录后 URL:', page.url())

  // ---- 录题页：上传那张题图 ----
  await page.goto(BASE + '/capture', { waitUntil: 'domcontentloaded' })
  await wait(2500)

  // ⚠️ UploadImage 组件是「先选文件、再点上传按钮」两步 —— 只 uploadFile 不会上传
  const fileInput = await page.$('input[data-testid="file-input"]') || await page.$('input[type=file]')
  console.log('找到文件输入框:', !!fileInput)
  await fileInput.uploadFile(IMG)
  await wait(1200)

  const clicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(
      (b) => /上传\s*\d+\s*张/.test(b.innerText) || (b.innerText.includes('上传') && b.innerText.includes('张'))
    )
    if (!btn) return { clicked: false, buttons: [...document.querySelectorAll('button')].map((b) => b.innerText.trim()).filter(Boolean).slice(0, 12) }
    btn.click()
    return { clicked: true, label: btn.innerText.trim() }
  })
  console.log('点上传按钮:', JSON.stringify(clicked))
  await wait(2500)
  console.log('已上传，等待 OCR（强模型约 21 秒）...')

  // 等 OCR 出结果
  let ok = false
  for (let i = 0; i < 90; i++) {
    await wait(2000)
    const n = await page.evaluate(() => document.querySelectorAll('.ocr-block').length)
    if (n > 0) { ok = true; console.log('OCR 完成，block 数:', n); break }
    if (i % 5 === 4) console.log('  ...等待中', (i + 1) * 2, 's')
  }
  if (!ok) { console.log('!! OCR 超时'); await page.screenshot({ path: SHOT_DIR + '/e2e-timeout.png' }); await browser.close(); return }

  await wait(1500)

  // ---- 检查 1: 题图卡片 ----
  const fig = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.ocr-figure-card')]
    return cards.map((c) => {
      const img = c.querySelector('div')
      const cs = img ? getComputedStyle(img) : null
      return {
        w: cs ? cs.width : null,
        h: cs ? cs.height : null,
        hasBg: cs ? !!cs.backgroundImage && cs.backgroundImage !== 'none' : false,
        bg: cs ? cs.backgroundImage.slice(0, 90) : null,
      }
    })
  })
  console.log('\n[检查1] 题图卡片:', JSON.stringify(fig))

  // ---- 检查 2: KaTeX 红字 ----
  const katex = await page.evaluate(() => {
    const errs = [...document.querySelectorAll('.katex-error')].map((e) => e.innerText)
    // 查红色文字（KaTeX 出错时的 style）
    const reds = []
    document.querySelectorAll('.ocr-block-content *').forEach((el) => {
      const cs = getComputedStyle(el)
      if (cs.color === 'rgb(204, 0, 0)') reds.push(el.innerText)
    })
    return { errs, reds }
  })
  console.log('[检查2] katex-error:', JSON.stringify(katex.errs), ' 红字:', JSON.stringify(katex.reds))

  // ---- 检查 3: 填空横线 + 符号疑点 ----
  const txt = await page.evaluate(() => {
    const card = document.querySelector('.n-card')
    return card ? card.innerText : ''
  })
  console.log('[检查3] 含 "____":', txt.includes('____'), ' 含 "PE/OA":', txt.includes('PE/OA'))

  const hints = await page.evaluate(() =>
    [...document.querySelectorAll('.ocr-hints .n-tag')].map((e) => e.innerText.trim())
  )
  console.log('[检查4] 符号疑点提示:', JSON.stringify(hints))

  await page.screenshot({ path: SHOT_DIR + '/e2e-capture.png', fullPage: true })

  // ---- 检查 5: 点提示一键改 ----
  if (hints.length) {
    await page.evaluate(() => {
      const tag = document.querySelector('.ocr-hints .n-tag')
      tag.click()
    })
    await wait(1200)
    const after = await page.evaluate(() => {
      const card = document.querySelector('.n-card')
      return card ? card.innerText : ''
    })
    console.log('[检查5] 一键改后含 "PE∥OA":', after.includes('PE∥OA'), ' 仍含 "PE/OA":', after.includes('PE/OA'))
  }

  // ---- 检查 6: 存入题库（改完的内容要能入库） ----
  const saved = await page.evaluate(async () => {
    const btn = [...document.querySelectorAll('button')].find((b) => b.innerText.includes('存入题库'))
    if (!btn) return { clicked: false }
    btn.click()
    return { clicked: true }
  })
  console.log('[检查6] 点入库:', JSON.stringify(saved))
  await wait(4000)
  const toast = await page.evaluate(() => document.body.innerText.match(/已入库（第 \d+ 题）/)?.[0] || '')
  console.log('[检查6] 入库提示:', toast || '(无)')

  // ---- 检查 7: 列表页缩略图 ----
  await page.goto(BASE + '/questions', { waitUntil: 'domcontentloaded' })
  await wait(4000)
  const list = await page.evaluate(() => {
    const ths = [...document.querySelectorAll('th')].map((t) => t.innerText.trim())
    const imgs = [...document.querySelectorAll('.figure-thumb img')].map((i) => ({
      w: i.naturalWidth, h: i.naturalHeight, src: i.src.slice(0, 30),
    }))
    return { ths, thumbCount: imgs.length, imgs: imgs.slice(0, 3) }
  })
  console.log('[检查7] 列表表头:', JSON.stringify(list.ths))
  console.log('[检查7] 缩略图:', list.thumbCount, JSON.stringify(list.imgs))
  await page.screenshot({ path: SHOT_DIR + '/e2e-list.png', fullPage: true })

  // ---- 检查 8: 详情页显示题图 ----
  const firstId = await page.evaluate(() => {
    const el = [...document.querySelectorAll('td')].find((td) => /^\d+$/.test(td.innerText.trim()))
    return el ? el.innerText.trim() : ''
  })
  if (firstId) {
    await page.goto(BASE + '/questions/' + firstId, { waitUntil: 'domcontentloaded' })
    await wait(3500)
    const det = await page.evaluate(() => {
      const box = document.querySelector('.figure-box')
      const img = box ? box.querySelector('img') : null
      return {
        hasBox: !!box,
        hasImg: !!img,
        nat: img ? [img.naturalWidth, img.naturalHeight] : null,
        text: box ? box.innerText.trim().slice(0, 60) : '',
      }
    })
    console.log('[检查8] 详情页题图:', JSON.stringify(det), ' id=', firstId)
    await page.screenshot({ path: SHOT_DIR + '/e2e-detail.png', fullPage: true })
  }

  await browser.close()
  console.log('\n=== 验收结束 ===')
}

main().catch((e) => { console.error('E2E 失败:', e); process.exit(1) })
