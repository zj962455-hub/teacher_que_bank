/**
 * 无头验证：老师「上传 → OCR → 入库」主链路（灰度试用前必须真跑通）
 *
 * 验证什么
 * --------
 * 1. 录题页上传一张真实试卷图 → 上传成功
 * 2. **上传后 OCR 面板拿到图片**（这里有个真 bug：UploadImage 从来没 emit 过
 *    `uploaded`，CapturePage 的 currentImage 永远是空 → OCR 按钮点不动）
 * 3. 点「开始识别」→ OCR 出结果（blocks 非空）
 * 4. 校对区能显示识别出的文字
 *
 * 跑法：
 *   cd lesson-03
 *   node scripts/verify-capture-flow.cjs
 *
 * 环境变量：
 *   VERIFY_BASE   默认 https://tqb.lanhu-lab.top
 *   VERIFY_USER   默认 test2
 *   VERIFY_PASS   默认 abc123
 *   VERIFY_IMAGE  默认本目录下的 fixture 图片（不存在则跳过上传步骤）
 */

const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test2'
const PASS = process.env.VERIFY_PASS || 'abc123'
const IMAGE = process.env.VERIFY_IMAGE || path.join(__dirname, 'fixture', 'sample.png')

const errors = []
const requests = []

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
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, val)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    },
    placeholder,
    value,
  )
}

async function clickButton(page, text) {
  const clicked = await page.evaluate((t) => {
    const btn = [...document.querySelectorAll('button')].find((b) =>
      b.innerText.replace(/\s+/g, '').includes(t.replace(/\s+/g, '')),
    )
    if (!btn) return false
    btn.click()
    return true
  }, text)
  if (!clicked) throw new Error(`找不到按钮「${text}」`)
}

async function main() {
  if (!fs.existsSync(IMAGE)) {
    console.log(`⚠️  fixture 不存在：${IMAGE}`)
    console.log('   先造一张：sips -s format png 输入图 --out scripts/fixture/sample.png')
    process.exit(2)
  }

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
  page.on('response', (r) => {
    const u = r.url()
    if (u.includes('/api/')) {
      requests.push(`${r.status()} ${u.replace(BASE, '').split('?')[0]}`)
    }
  })

  const results = []
  const check = (name, ok, extra = '') => {
    results.push({ name, ok, extra })
    console.log(`  ${ok ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
  }

  try {
    // === 1. 登录 ===
    console.log('\n[1] 登录')
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await wait(1500)
    await fillInput(page, '用户名', USER)
    await fillInput(page, '密码', PASS)
    await clickButton(page, '登录')
    await wait(2500)
    check('登录成功', !page.url().includes('/login'), page.url())

    // === 2. 进录题页 ===
    console.log('\n[2] 进录题页')
    await page.goto(`${BASE}/capture`, { waitUntil: 'domcontentloaded' })
    await wait(2000)
    check('录题页打开', await page.evaluate(() => document.body.innerText.includes('录题')))

    // === 3. 上传 ===
    console.log('\n[3] 上传试卷图')
    const input = await page.$('input[type=file]')
    if (!input) throw new Error('找不到文件输入框')
    await input.uploadFile(IMAGE)
    await wait(800)
    await clickButton(page, '上传')
    await wait(4000)

    const uploadedText = await page.evaluate(() => document.body.innerText)
    check('上传成功', uploadedText.includes('已上传'), uploadedText.match(/已上传 \d+ 张/)?.[0] || '')

    // === 4. OCR 面板拿到图片了吗（关键 bug 点）===
    const ocrReady = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) =>
        b.innerText.includes('开始识别'),
      )
      if (!btn) return { found: false }
      return { found: true, disabled: btn.disabled }
    })
    check(
      'OCR「开始识别」按钮存在且可点',
      ocrReady.found && ocrReady.disabled === false,
      ocrReady.found ? `disabled=${ocrReady.disabled}` : '按钮没找到',
    )

    // === 5. 跑 OCR ===
    console.log('\n[4] 跑 OCR（等结果）')
    if (ocrReady.found && ocrReady.disabled === false) {
      await clickButton(page, '开始识别')
      let ocrText = ''
      for (let i = 0; i < 20; i++) {
        await wait(3000)
        ocrText = await page.evaluate(() => document.body.innerText)
        if (/识别完成|识别成功|校对|保存|题干/.test(ocrText)) break
      }
      const hasResult = /校对|保存到题库|识别结果|content/i.test(ocrText)
      check('OCR 出结果', hasResult, ocrText.slice(0, 120).replace(/\n+/g, ' | '))
    } else {
      check('OCR 出结果', false, '跳过 —— 上一步按钮不可点')
    }
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== 请求记录 ===')
  console.log(requests.join('\n'))

  const unexpected = errors.filter((e) => !/401|403|404/.test(e))
  console.log('\n=== 运行时错误 ===')
  console.log(unexpected.length ? unexpected.join('\n') : '（无）')

  const failed = results.filter((r) => !r.ok)
  console.log('\n==============================================')
  console.log(`  ${results.length - failed.length}/${results.length} 项通过`)
  console.log('==============================================')
  process.exit(failed.length ? 1 : 0)
}

main()
