/**
 * 无头验证：figure 裁图预览 + 引擎标签 + 一键入库（lesson-35 修复回归）
 *
 * 上一版 verify-ocr-queue.cjs 有三个断言口径不对（请求记录里没有方法名、
 * 入库后页面自动跳转导致读不到 toast、naive-ui 下拉要真实 click），
 * 这一版按真实行为重写，并且补上「切历史逐张看图形裁图」这条。
 *
 * 跑法：
 *   cd lesson-03
 *   VERIFY_IMAGES="a.png,b.png,c.png,d.png" node scripts/verify-ocr-figure.cjs
 */

const puppeteer = require('puppeteer-core')
const fs = require('fs')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test2'
const PASS = process.env.VERIFY_PASS || 'abc123'
const IMAGES = (process.env.VERIFY_IMAGES || '').split(',').map((s) => s.trim()).filter(Boolean)

const errors = []
const apiCalls = []
let saveResp = null

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

// 读当前页面上的图形裁图状态
async function readFigureState(page) {
  return await page.evaluate(() => {
    const figs = [...document.querySelectorAll('.ocr-figure-crop')].map((el) => {
      const cs = getComputedStyle(el)
      return {
        bg: cs.backgroundImage,
        pos: cs.backgroundPosition,
        size: cs.backgroundSize,
        w: Math.round(el.getBoundingClientRect().width),
        h: Math.round(el.getBoundingClientRect().height),
        text: el.innerText.trim(),
      }
    })
    const blocks = [...document.querySelectorAll('.ocr-block')].map((b) => b.innerText).join('\n')
    const katexText = [...document.querySelectorAll('.katex')].map((k) => k.innerText).join(' ')
    const img = document.querySelector('.n-image img, img')
    return {
      figs,
      blocks,
      katexText,
      origSize: img ? img.naturalWidth + 'x' + img.naturalHeight : '',
    }
  })
}

// 打开历史下拉，返回所有选项文案
async function openHistoryDropdown(page) {
  const clicked = await page.evaluate(() => {
    const sel = document.querySelector('.n-base-selection')
    if (!sel) return false
    sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    sel.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    sel.click()
    return true
  })
  if (!clicked) return []
  await wait(1200)
  const labels = await page.evaluate(() => {
    const opts = [...document.querySelectorAll('.n-base-select-option')]
    return opts.map((o) => o.innerText.trim()).filter(Boolean)
  })
  return labels
}

// 点第 n 个下拉选项
async function pickHistoryOption(page, index) {
  const ok = await page.evaluate((i) => {
    const opts = [...document.querySelectorAll('.n-base-select-option')]
    if (!opts[i]) return false
    opts[i].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    opts[i].click()
    return true
  }, index)
  if (!ok) throw new Error('下拉里没有第 ' + (index + 1) + ' 个选项')
  await wait(2500)
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
  page.on('request', (req) => {
    const u = req.url()
    if (u.includes('/api/')) {
      apiCalls.push(req.method() + ' ' + u.replace(BASE, '').split('?')[0])
    }
  })
  page.on('response', async (r) => {
    const u = r.url()
    if (u.includes('/api/questions/from-ocr')) {
      let body = null
      try {
        body = await r.json()
      } catch (e) {
        body = null
      }
      saveResp = { status: r.status(), body }
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

    console.log('\n[3] 一次选 ' + IMAGES.length + ' 张图并上传')
    const input = await page.$('input[type=file]')
    if (!input) throw new Error('找不到文件输入框')
    await input.uploadFile(...IMAGES)
    await wait(800)
    await clickButton(page, '上传')
    await wait(5000)
    const upText = await page.evaluate(() => document.body.innerText)
    check('全部图片上传成功', upText.includes('已上传 ' + IMAGES.length + ' 张'),
      (upText.match(/已上传 \d+ 张/) || [])[0] || '')

    console.log('\n[4] 等队列跑完')
    let done = 0
    const deadline = Date.now() + 300000
    while (Date.now() < deadline) {
      await wait(2000)
      const d = await page.evaluate(() => {
        const alert = [...document.querySelectorAll('.n-alert')].map((a) => a.innerText).join(' ')
        const m = alert.match(/已识别 (\d+) 张/)
        return m ? parseInt(m[1], 10) : -1
      })
      if (d !== done && d >= 0) {
        done = d
        console.log('     已识别 ' + d + '/' + IMAGES.length)
      }
      if (done >= IMAGES.length) break
    }
    check('全部 ' + IMAGES.length + ' 张识别完', done >= IMAGES.length, '已识别 ' + done + ' 张')

    const ocrPosts = apiCalls.filter((c) => c.startsWith('POST') && /\/api\/ocr\/(\s|$)/.test(c)).length
    check('每张图都发起了 OCR 请求', ocrPosts >= IMAGES.length, 'POST /api/ocr/ 共 ' + ocrPosts + ' 次')

    console.log('\n[5] 切历史逐张看结果（图形裁图 + 角符号）')
    const labels = await openHistoryDropdown(page)
    check('历史下拉有记录', labels.length > 0, labels.length + ' 条')
    check('历史下拉带引擎标签', labels.some((l) => /强模型|轻量/.test(l)),
      labels.slice(0, 3).join(' / ') || '(空)')

    let figOk = 0
    let figSeen = 0
    let angleOk = 0
    const perImage = []
    const lookAt = Math.min(IMAGES.length, labels.length)
    for (let i = 0; i < lookAt; i++) {
      await pickHistoryOption(page, i)
      const st = await readFigureState(page)
      const hasFig = st.figs.length > 0
      const cropReal = st.figs.some(
        (f) => f.bg && f.bg !== 'none' && f.bg.indexOf('blob:') >= 0 && f.w > 10 && f.h > 10,
      )
      const hasAngle = /∠|\\angle/.test(st.blocks + ' ' + st.katexText)
      if (hasFig) figSeen++
      if (cropReal) figOk++
      if (hasAngle) angleOk++
      perImage.push({
        label: labels[i],
        blocks: st.blocks.length,
        fig: st.figs.length,
        crop: st.figs.map((f) => f.w + 'x' + f.h + ' bg=' + f.bg.slice(0, 26) + ' pos=' + f.pos),
        angle: hasAngle,
        orig: st.origSize,
      })
      console.log(
        '     [' + (i + 1) + '] ' + (labels[i] || '').slice(0, 46) +
          ' · blocks ' + st.blocks.length + ' 字 · figure ' + st.figs.length +
          ' · 裁出有效 ' + (cropReal ? '是' : '否') +
          ' · ∠ ' + (hasAngle ? '有' : '无') +
          (st.figs.length ? ' · ' + st.figs[0].w + 'x' + st.figs[0].h + ' pos=' + st.figs[0].pos : ''),
      )
    }
    check('图形块在页面上裁出真实图形（不是空白）', figOk > 0,
      figOk + '/' + lookAt + ' 张裁出有效图形（共 ' + figSeen + ' 张含 figure 块）')
    check('角符号渲染成 ∠', angleOk > 0, angleOk + '/' + lookAt + ' 张含 ∠')

    console.log('\n[6] 一键入库（看接口返回，不看 toast）')
    await page.keyboard.press('Escape')
    await wait(600)
    try {
      await clickButton(page, '存入题库')
      await wait(6000)
      check(
        '一键入库接口 200',
        !!saveResp && saveResp.status === 200,
        saveResp ? 'HTTP ' + saveResp.status + ' · ' + JSON.stringify(saveResp.body).slice(0, 160) : '没抓到请求',
      )
    } catch (e) {
      check('一键入库接口 200', false, e.message)
    }
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== API 调用记录 ===')
  const uniq = []
  const seen = {}
  for (const c of apiCalls) {
    const key = c.split(' ')[0] + ' ' + c.split(' ')[1].replace(/[0-9a-f]{8}-[0-9a-f-]{27}/, '<id>')
    if (!seen[key]) {
      seen[key] = 1
      uniq.push(c)
    } else {
      seen[key]++
    }
  }
  console.log(uniq.join('\n'))

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
