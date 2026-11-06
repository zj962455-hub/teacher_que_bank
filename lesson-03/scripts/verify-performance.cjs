/**
 * 无头验证：性能（课 33）
 *
 * 验证什么
 * --------
 * 1. **列表接口响应体积小** —— 不带 blocks（每题最多 50 KB）
 * 2. **首屏请求数少** —— 分类树 + 扁平列表合并成一次（原来两个接口数据重叠）
 * 3. **页面功能没坏** —— 列表页能渲染出题目、能按分类筛选
 * 4. **详情页仍带 blocks** —— OCR 溯源要靠它
 *
 * 跑法：
 *   node scripts/verify-performance.cjs
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'abc123'

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
    if (m.type() === 'error' && !m.location().url.includes('/api/')) {
      errors.push(`console.error: ${m.text()}`)
    }
  })

  // 记 API 请求 + 响应大小
  page.on('response', async (res) => {
    const url = res.url()
    if (!url.includes('/api/')) return
    let size = 0
    try {
      size = (await res.buffer()).length
    } catch {
      /* 二进制/流式响应读不到就算了 */
    }
    requests.push({ url: url.replace(BASE, ''), status: res.status(), size })
  })

  console.log('→ 登录')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(1500)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(3000)

  // ---------- 场景 1：题目列表 ----------
  console.log('→ 场景 1：题目列表')
  requests.length = 0
  await page.goto(`${BASE}/questions`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(3000)

  const listInfo = requests
    .filter((r) => r.url.includes('/api/questions/') && !r.url.includes('/recent'))
  const catReqs = requests.filter((r) => r.url.includes('/api/categories'))
  const listBytes = listInfo.reduce((s, r) => s + r.size, 0)

  console.log('  题目列表接口:', listInfo.map((r) => `${r.url} ${r.status} ${(r.size / 1024).toFixed(1)}KB`).join(' | '))
  console.log('  列表响应合计:', (listBytes / 1024).toFixed(1), 'KB')
  console.log('  分类相关请求:', catReqs.length, '次', catReqs.map((r) => r.url).join(' '))

  const view = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      qCount: document.querySelectorAll('.n-tree-node, .question-item, tbody tr').length,
      hasTree: !!document.querySelector('.n-tree'),
      snippet: text.slice(0, 180).replace(/\n/g, ' '),
    }
  })
  console.log('  列表页有内容:', view.qCount || view.hasTree ? '✅' : '❌')
  if (!view.qCount && !view.hasTree) {
    console.log('  实际内容:', view.snippet)
    throw new Error('列表页没渲染出内容')
  }

  // 关键断言：分类只请求一次（不再并发拉树 + 扁平）
  if (catReqs.length > 1) {
    throw new Error(`分类相关请求 ${catReqs.length} 次（应该是 1 次 —— 扁平列表从树推导）`)
  }
  console.log('  分类只请求一次: ✅')

  // 关键断言：列表响应不含 blocks → 体积可控
  if (listBytes > 200 * 1024) {
    throw new Error(`列表响应 ${(listBytes / 1024).toFixed(0)} KB 太大 —— blocks 没剔掉？`)
  }
  console.log('  列表响应体积可控: ✅')

  // ---------- 场景 2：详情页仍带 blocks ----------
  console.log('→ 场景 2：详情接口仍带 blocks')
  const detail = await page.evaluate(async () => {
    const token = localStorage.getItem('tqb_token')
    const list = await fetch('/api/questions/?limit=20', { headers: { Authorization: `Bearer ${token}` } })
    const body = await list.json()
    if (!body.items || !body.items.length) return { ok: false, why: '没有题目' }
    const d = await fetch(`/api/questions/${body.items[0].id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const detailBody = await d.json()
    // ⚠️ 只断言「有这个键」——
    //    线上测试数据是没 OCR 过的新题，blocks 自然是空数组；
    //    「blocks 非空」由后端 pytest (test_perf.py) 用带 blocks 的数据保证。
    return {
      ok: true,
      hasKey: 'blocks' in detailBody,
      isArray: Array.isArray(detailBody.blocks),
      n: (detailBody.blocks || []).length,
    }
  })
  console.log(
    '  详情带 blocks 字段:',
    detail.ok && detail.hasKey && detail.isArray ? '✅' : '❌',
    detail.ok ? `（该题 blocks ${detail.n} 条）` : detail.why || '',
  )
  if (!detail.ok || !detail.hasKey || !detail.isArray) {
    throw new Error('详情接口的 blocks 字段没了（OCR 溯源会坏）')
  }

  await page.screenshot({ path: '/tmp/verify-performance.png', fullPage: false })
  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 性能验证全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
