/**
 * 无头验证：多图排队 OCR 回归（lesson-35 修复）
 *
 * 验证什么
 * --------
 * 1. 一次上传 4 张 → 全部进 OCR 队列（以前只跑最后 1 张）
 * 2. 排队进度提示：本次共 4 张 / 已识别 N 张 / 剩余 M 张
 * 3. 角符号：KaTeX 里真的渲染出 \angle（∠），不是 Z / A.A
 * 4. 图形预览：figure 块按 bbox 从原图裁出来，不是空白
 * 5. 历史下拉带「强模型」引擎标签
 * 6. 全部完成后一键入库成功
 *
 * 跑法：
 *   cd lesson-03
 *   VERIFY_IMAGES="/tmp/ocr-e2e/a.png,/tmp/ocr-e2e/b.png" node scripts/verify-ocr-queue.cjs
 */

const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test2'
const PASS = process.env.VERIFY_PASS || 'abc123'
const IMAGES = (process.env.VERIFY_IMAGES || '').split(',').map((s) => s.trim()).filter(Boolean)

const errors = []
const requests = []
const snapshots = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function fillInput(page, placeholder, value) {
  await page.evaluate(
    (ph, val) => {
      const el = [...document.querySelectorAll('input')].find(
        (i) => i.placeholder && i.placeholder.includes(ph),
      )
      if (!el) throw new Error('找不到 placeholder 含 "' + ph + '" 的输入框')
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
  if (!clicked) throw new Error('找不到按钮「' + text + '」')
}

async function main() {
  if (!IMAGES.length) {
    console.log('⚠️  没给 VERIFY_IMAGES')
    process.exit(2)
  }
  for (const f of IMAGES) {
    if (!fs.existsSync(f)) {
      console.log('⚠️  图片不存在：' + f)
      process.exit(2)
    }
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1000 })

  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('console.error: ' + m.text())
  })
  page.on('response', (r) => {
    const u = r.url()
    if (u.includes('/api/')) {
      requests.push(r.status() + ' ' + u.replace(BASE, '').split('?')[0])
    }
  })

  const results = []
  const check = (name, ok, extra = '') => {
    results.push({ name, ok })
    console.log('  ' + (ok ? '✅' : '❌') + ' ' + name + (extra ? ' — ' + extra : ''))
  }

  try {
    console.log('\n[1] 登录')
    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await wait(1500)
    await fillInput(page, '用户名', USER)
    await fillInput(page, '密码', PASS)
    await clickButton(page, '登录')
    await wait(2500)
    check('登录成功', !page.url().includes('/login'), page.url())

    console.log('\n[2] 进录题页')
    await page.goto(BASE + '/capture', { waitUntil: 'domcontentloaded' })
    await wait(2000)
    check('录题页打开', await page.evaluate(() => document.body.innerText.includes('录题')))

    console.log('\n[3] 一次选 ' + IMAGES.length + ' 张图')
    const input = await page.$('input[type=file]')
    if (!input) throw new Error('找不到文件输入框')
    await input.uploadFile(...IMAGES)
    await wait(800)
    const selText = await page.evaluate(() => document.body.innerText)
    check(
      '文件选择器收到 ' + IMAGES.length + ' 张',
      selText.includes(IMAGES.length + ' 个文件已选'),
      (selText.match(/\d+ 个文件已选/) || [])[0] || '',
    )

    console.log('\n[4] 点上传')
    await clickButton(page, '上传')
    await wait(5000)
    const upText = await page.evaluate(() => document.body.innerText)
    check(
      '全部图片上传成功',
      upText.includes('已上传 ' + IMAGES.length + ' 张'),
      (upText.match(/已上传 \d+ 张/) || [])[0] || '',
    )

    console.log('\n[5] 等 4 张排队识别完（每张约 21s）')
    let lastDone = -1
    let queueAlertSeen = false
    let finished = false
    const deadline = Date.now() + 300000

    while (Date.now() < deadline) {
      await wait(2000)
      const snap = await page.evaluate(() => {
        const text = document.body.innerText
        const alert = [...document.querySelectorAll('.n-alert')].map((a) => a.innerText).join(' | ')
        const blocks = [...document.querySelectorAll('.ocr-block')].map((b) => b.innerText).join('\n')
        const figs = [...document.querySelectorAll('.ocr-figure-crop')].map((el) => {
          const cs = getComputedStyle(el)
          return {
            bg: cs.backgroundImage,
            pos: cs.backgroundPosition,
            size: cs.backgroundSize,
            w: el.getBoundingClientRect().width,
            h: el.getBoundingClientRect().height,
            text: el.innerText.trim(),
          }
        })
        const m = alert.match(/已识别 (\d+) 张/)
        const r = alert.match(/剩余 (\d+) 张/)
        const t = alert.match(/本次共 (\d+) 张/)
        return {
          alert,
          done: m ? parseInt(m[1], 10) : -1,
          rest: r ? parseInt(r[1], 10) : -1,
          total: t ? parseInt(t[1], 10) : -1,
          blocks,
          figs,
          hasKatex: document.querySelectorAll('.katex').length,
          body: text,
        }
      })

      if (snap.alert) queueAlertSeen = true
      if (snap.done !== lastDone && snap.done >= 0) {
        lastDone = snap.done
        snapshots.push({ done: snap.done, blocks: snap.blocks, figs: snap.figs, body: snap.body })
        console.log(
          '     已识别 ' + snap.done + '/' + snap.total + ' 剩余 ' + snap.rest +
            ' · blocks ' + (snap.blocks ? snap.blocks.length : 0) + ' 字 · figure ' + snap.figs.length +
            ' · katex ' + snap.hasKatex,
        )
      }
      if (snap.done >= IMAGES.length) {
        finished = true
        break
      }
    }

    check('排队进度提示出现过', queueAlertSeen)
    check('全部 ' + IMAGES.length + ' 张都识别完', finished, '已识别 ' + lastDone + ' 张')

    const ocrPosts = requests.filter((r) => r.startsWith('20') && r.includes('POST /api/ocr/')).length
    check(
      '每张图都发起了 OCR 请求',
      ocrPosts >= IMAGES.length,
      'POST /api/ocr/ 共 ' + ocrPosts + ' 次',
    )

    // 角符号
    const angleHits = snapshots.filter((s) => /∠|\\angle/.test(s.blocks + s.body))
    check(
      '角符号识别正确（渲染出 ∠）',
      angleHits.length > 0,
      angleHits.length + '/' + snapshots.length + ' 张快照里出现 ∠',
    )
    const badAngle = snapshots.filter((s) => /(^|[^A-Za-z])Z[A-Za-z]*\s*=|A\.A/.test(s.blocks))
    check('没有出现旧的错误形态（ZA / A.A）', badAngle.length === 0, badAngle.length + ' 处')

    // 图形预览
    const withFig = snapshots.filter((s) => s.figs.length > 0)
    const figOk = withFig.filter(
      (s) => s.figs.some((f) => f.bg && f.bg !== 'none' && f.bg.includes('blob:') && f.w > 10 && f.h > 10),
    )
    check(
      '图形块按 bbox 从原图裁出来（不是空白）',
      figOk.length > 0,
      withFig.length
        ? withFig.length + ' 张有 figure 块，其中 ' + figOk.length + ' 张裁出有效图形 ' +
          (withFig[0].figs[0] ? JSON.stringify(withFig[0].figs[0]).slice(0, 120) : '')
        : '没有任何快照出现 figure 块',
    )

    // 引擎标签
    const historyLabels = await page.evaluate(() => {
      const sel = document.querySelector('.n-base-selection')
      if (!sel) return ''
      sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      return ''
    })
    await wait(1200)
    const dropdownText = await page.evaluate(() => {
      const dd = document.querySelector('.n-base-select-menu')
      return dd ? dd.innerText : ''
    })
    const engineTagSeen = /强模型|轻量/.test(dropdownText)
    check('历史下拉带引擎标签（强模型/轻量）', engineTagSeen, dropdownText.split('\n')[0] || '')

    console.log('\n[6] 一键入库')
    await page.keyboard.press('Escape')
    await wait(500)
    let saved = false
    try {
      await clickButton(page, '存入题库')
      await wait(6000)
      const t = await page.evaluate(() => document.body.innerText)
      saved = /已入库（第 \d+ 题）/.test(t)
      check('一键入库成功', saved, (t.match(/已入库（第 \d+ 题）/) || [])[0] || t.slice(-160).replace(/\n+/g, ' | '))
    } catch (e) {
      check('一键入库成功', false, e.message)
    }
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== 请求记录 ===')
  console.log(requests.join('\n'))

  const unexpected = errors.filter((e) => !/401|403|404|Failed to load resource/.test(e))
  console.log('\n=== 运行时错误 ===')
  console.log(unexpected.length ? unexpected.join('\n') : '（无）')

  const failed = results.filter((r) => !r.ok)
  console.log('\n==============================================')
  console.log('  ' + (results.length - failed.length) + '/' + results.length + ' 项通过')
  console.log('==============================================')
  process.exit(failed.length ? 1 : 0)
}

main()
