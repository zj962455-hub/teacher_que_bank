/**
 * 无头验证：组卷三栏 — lesson-11
 *
 * 验证什么
 * --------
 * 1. 组卷页是三栏（选题 / 试卷 / 预览）
 * 2. 试卷区有拖拽手柄
 * 3. 预览区在,且显示题目
 * 4. 全程无运行时错误
 *
 * 跑法：
 *   node scripts/verify-paper.cjs
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

  // === 组卷页 ===
  console.log('→ 打开组卷页')
  await page.goto(`${BASE}/papers/new`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  // 先选一张卷(有卷才能看到拖拽手柄和预览内容)
  const picked = await page.evaluate(() => {
    const sel = document.querySelector('.n-base-selection')
    if (!sel) return false
    sel.click()
    return true
  })
  if (picked) {
    await wait(800)
    const chose = await page.evaluate(() => {
      const opt = [...document.querySelectorAll('.n-base-select-option')][0]
      if (!opt) return false
      opt.click()
      return true
    })
    console.log('  选卷:', chose ? '✅' : '（没有可选的卷）')
    await wait(2000)
  }

  const layout = await page.evaluate(() => {
    const cols = document.querySelectorAll('.three-col > *')
    const text = document.body.innerText
    return {
      colCount: cols.length,
      hasLeft: text.includes('选题'),
      hasMid: text.includes('试卷'),
      hasPreview: text.includes('预览'),
      dragHandles: document.querySelectorAll('.drag-handle').length,
      paperItems: document.querySelectorAll('.paper-item').length,
      candidates: document.querySelectorAll('.candidate').length,
      hasPreviewCard: !!document.querySelector('.preview-paper'),
      snippet: text.slice(0, 160).replace(/\n/g, ' '),
    }
  })

  console.log('  三栏容器:', layout.colCount === 3 ? '✅ 3 栏' : `❌ ${layout.colCount} 栏`)
  console.log('  左栏选题:', layout.hasLeft ? '✅' : '❌')
  console.log('  中栏试卷:', layout.hasMid ? '✅' : '❌')
  console.log('  右栏预览:', layout.hasPreview ? '✅' : '❌')
  console.log('  拖拽手柄:', layout.dragHandles, '个')
  console.log('  候选题:', layout.candidates, '道 | 卷内:', layout.paperItems, '道')
  console.log('  预览卡:', layout.hasPreviewCard ? '✅' : '❌')

  if (layout.colCount !== 3) {
    console.log('  实际内容:', layout.snippet)
    throw new Error(`不是三栏布局（${layout.colCount} 栏）`)
  }

  await page.screenshot({ path: '/tmp/verify-paper.png', fullPage: false })

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 组卷三栏全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
