/**
 * 无头验证：公开举报入口（lesson-43 · 公安备案 · 安全评估第五条第（六）项）
 *
 * 验证什么
 * --------
 * 1. 访客**未登录**打开公开分享页 → 页面能出，且**看得到**「举报违法有害信息」按钮
 *    （官方要「公开举报、举报方式等信息举报渠道的畅通」—— 入口必须对访客可见）
 * 2. 点按钮 → 举报弹窗打开，字段齐全（举报类型 / 举报说明 / 联系方式）
 * 3. 填表提交 → 弹窗切换成「已受理」并显示**受理编号**（形如 RXXXXXXXXXXX）
 * 4. 举报人凭编号能查到进展（后端接口，返回状态「待受理」）
 * 5. 全程无运行时错误
 *
 * 跑法：
 *   SHARE_TOKEN=<token> node scripts/verify-report.cjs
 *
 * 环境变量：
 *   VERIFY_BASE    默认 https://tqb.lanhu-lab.top
 *   SHARE_TOKEN    要打开的分享 token（必填）
 *   PROBE_MARKER   提交时填进「联系方式」的标记（默认 probe-verify@example.com），
 *                  跑完用它把测试举报记录删掉
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const TOKEN = process.env.SHARE_TOKEN || ''
const MARKER = process.env.PROBE_MARKER || 'probe-verify@example.com'

const errors = []
const results = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

function check(name, ok, extra = '') {
  results.push({ name, ok })
  console.log(`  ${ok ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
}

async function fillByPlaceholder(page, placeholder, value) {
  await page.evaluate(
    (ph, val) => {
      const el = [...document.querySelectorAll('input, textarea')].find(
        (i) => i.placeholder && i.placeholder.includes(ph),
      )
      if (!el) throw new Error(`找不到 placeholder 含 "${list.join('/')}" 的输入框`)
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
  if (!TOKEN) {
    console.error('缺 SHARE_TOKEN')
    process.exit(2)
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1500, height: 1000 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  console.log('→ 1) 访客未登录打开分享页')
  await page.goto(`${BASE}/share/${TOKEN}`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)

  const pageInfo = await page.evaluate(() => ({
    hasSharePage: !!document.querySelector('.shared-page'),
    hasReportBtn: [...document.querySelectorAll('button')].some(
      (b) => b.textContent.includes('举报违法有害信息'),
    ),
    loggedIn: !!localStorage.getItem('tqb_token'),
  }))
  check('分享页渲染出来了', pageInfo.hasSharePage)
  check('确实是未登录访客（本地无 token）', !pageInfo.loggedIn)
  check('访客可见「举报违法有害信息」按钮', pageInfo.hasReportBtn)

  if (!pageInfo.hasReportBtn) {
    await page.screenshot({ path: '/tmp/verify-report.png', fullPage: false })
    throw new Error('访客看不到举报按钮 —— 举报渠道不畅通')
  }

  console.log('→ 2) 点开举报弹窗')
  await clickByText(page, '举报违法有害信息')
  await wait(900)

  const modal = await page.evaluate(() => {
    const body = document.body.innerText
    return {
      hasTitle: body.includes('举报违法有害信息'),
      hasReason: body.includes('举报类型'),
      hasDetail: body.includes('举报说明'),
      hasContact: body.includes('联系方式'),
      hasSubmit: [...document.querySelectorAll('button')].some(
        (b) => b.textContent.trim() === '提交举报',
      ),
    }
  })
  check('弹窗标题正确', modal.hasTitle)
  check('有「举报类型」选择', modal.hasReason)
  check('有「举报说明」输入', modal.hasDetail)
  check('有「联系方式」输入', modal.hasContact)
  check('有「提交举报」按钮', modal.hasSubmit)

  console.log('→ 3) 填表并提交')
  await fillByPlaceholder(page, '请说明具体问题', '无头验收：内容含违法有害信息')
  await fillByPlaceholder(page, '手机号或邮箱', MARKER)
  await wait(300)
  await clickByText(page, '提交举报')
  await wait(2000)

  const done = await page.evaluate(() => {
    const el = document.querySelector('.report-no')
    return {
      hasNo: !!el,
      no: el ? el.textContent.trim() : '',
      body: document.body.innerText.slice(0, 400),
    }
  })
  check('提交后显示受理编号', done.hasNo, done.no)
  check(
    '受理编号格式正确（R + 11 位）',
    /^R[A-Z0-9]{11}$/.test(done.no),
    done.no,
  )

  await page.screenshot({ path: '/tmp/verify-report.png', fullPage: false })

  console.log('→ 4) 凭编号查进展')
  const track = await page.evaluate(async (no) => {
    const r = await fetch('/api/reports/track/' + no)
    return { status: r.status, body: await r.json() }
  }, done.no)
  check('凭编号可查进展（HTTP 200）', track.status === 200, String(track.status))
  check('状态为「待受理」', track.body && track.body.status_label === '待受理',
    track.body ? track.body.status_label : '')
  check('进展不回显举报人联系方式（隐私）',
    track.body && !JSON.stringify(track.body).includes(MARKER))

  console.log('')
  const failed = results.filter((r) => !r.ok)
  if (errors.length) {
    console.log('运行时错误:')
    errors.forEach((e) => console.log('  ⚠️ ' + e))
  }
  console.log(`结果：${results.length - failed.length}/${results.length} 通过`)
  if (failed.length || errors.length) {
    console.log('❌ 验收未通过')
    process.exit(1)
  }
  console.log('✅ 公开举报入口验收通过')
  console.log('   受理编号: ' + done.no)
}

main().catch((e) => {
  console.error('验收脚本异常:', e.message)
  process.exit(1)
})
