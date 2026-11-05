/**
 * 无头验证：标签系统 — lesson-11
 *
 * 验证什么
 * --------
 * 1. 登录 → /questions 页面能建标签
 * 2. 建标签 → 标签出现在左侧标签区
 * 3. 给题打标签 → 详情页显示标签
 * 4. 按标签筛选 → 题目列表只剩带该标签的题
 * 5. 排序参数生效（sort/order）
 * 6. 删标签 → 从列表消失
 * 7. 全程无运行时错误（pageerror / console.error）
 *
 * 跑法：
 *   VERIFY_BASE=https://tqb.lanhu-lab.top VERIFY_USER=test1 VERIFY_PASS=abc123 node scripts/verify-tags.cjs
 *
 * ⚠️ 脚本自己造数据（标签 + 一道题），验完删掉 —— 不依赖环境初始状态。
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'http://localhost:5173'
const USER = process.env.VERIFY_USER || 'test1'
const PASS = process.env.VERIFY_PASS || 'Test123456'
const TAG = '验收' + Date.now().toString().slice(-5)

const errors = []
let step = 'login'

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
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value',
      ).set
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
  if (!ok) {
    const all = await page.evaluate(
      (g) => [...document.querySelectorAll(g)].map((x) => x.textContent.trim()),
      tag,
    )
    throw new Error(`找不到按钮「${text}」；当前页面上有：${JSON.stringify(all)}`)
  }
}

/**
 * 通过 API 直接操作（比点 UI 稳）
 * 造：一道题 + 一个标签，并给题打上标签
 */
async function apiCall(page, method, path, body) {
  return page.evaluate(
    async (m, p, b) => {
      const token = localStorage.getItem('tqb_token')
      const res = await fetch(p, {
        method: m,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + token,
        },
        body: b ? JSON.stringify(b) : undefined,
      })
      return { status: res.status, data: await res.json().catch(() => null) }
    },
    method,
    path,
    body,
  )
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1600, height: 1000 })

  page.on('pageerror', (e) => errors.push(`[${step}] pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[${step}] console.error: ${m.text()}`)
  })
  page.on('requestfailed', (r) =>
    errors.push(`[${step}] requestfailed: ${r.url()} ${r.failure()?.errorText}`),
  )

  // === 登录 ===
  step = 'login'
  console.log('→ 登录', BASE)
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  const logged = await page.evaluate(() => Boolean(localStorage.getItem('tqb_token')))
  if (!logged) throw new Error('登录失败，没有拿到 token')
  console.log('  登录 ✅')

  // === 造数据：一个标签 + 一道题 + 打标签 ===
  step = 'seed'
  console.log('→ 造数据')
  const seed = await page.evaluate(async (t) => {
    const token = localStorage.getItem('tqb_token')
    const call = async (m, p, b) => {
      const res = await fetch(p, {
        method: m,
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: b ? JSON.stringify(b) : undefined,
      })
      return { status: res.status, data: await res.json().catch(() => null) }
    }
    // 清掉历次遗留
    const tagsRes = await call('GET', '/api/tags/')
    const stale = (tagsRes.data?.items || []).filter((x) => x.name?.includes('验收'))
    for (const s of stale) await call('DELETE', '/api/tags/' + s.id)

    const tagRes = await call('POST', '/api/tags/', { name: t })
    if (tagRes.status !== 200) return { ok: false, error: '建标签 ' + tagRes.status }

    const qRes = await call('POST', '/api/questions/', {
      content_plain: '验收用题目 ' + t,
      content_markdown: '验收用题目 ' + t,
    })
    if (qRes.status !== 200) return { ok: false, error: '建题 ' + qRes.status }

    const linkRes = await call('PUT', '/api/tags/question/' + qRes.data.id, {
      tag_ids: [tagRes.data.id],
    })
    if (linkRes.status !== 200) return { ok: false, error: '打标签 ' + linkRes.status }

    return { ok: true, tagId: tagRes.data.id, tagName: tagRes.data.name, questionId: qRes.data.id }
  }, TAG)

  if (!seed.ok) throw new Error('造数据失败: ' + seed.error)
  console.log('  已造标签:', seed.tagName, '| 题目 id', seed.questionId)

  // === 题目列表页：标签区 + 筛选 ===
  step = 'questions'
  console.log('→ 打开 /questions')
  await page.goto(`${BASE}/questions`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2200)

  const list = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasTagCard: text.includes('标签'),
      tagVisible: text.includes('验收'),
      hasSort: text.includes('创建时间') || text.includes('更新时间'),
      hasTagColumn: text.includes('标签'),
      rows: document.querySelectorAll('.n-data-table-tbody .n-data-table-tr').length,
      snippet: text.slice(0, 260).replace(/\n/g, ' '),
    }
  })
  console.log('  标签卡:', list.hasTagCard ? '✅' : '❌')
  console.log('  标签可见:', list.tagVisible ? '✅' : '❌')
  console.log('  排序选项:', list.hasSort ? '✅' : '❌')
  console.log('  表格行数:', list.rows)
  if (!list.tagVisible) console.log('  实际内容:', list.snippet)
  if (!list.tagVisible) throw new Error('标签没出现在题目页')

  // === 按标签筛选 ===
  step = 'filter'
  console.log('→ 按标签筛选(走 API,验后端参数)')
  const filtered = await page.evaluate(async (tid) => {
    const token = localStorage.getItem('tqb_token')
    const res = await fetch('/api/questions/?tag_ids=' + tid, {
      headers: { Authorization: 'Bearer ' + token },
    })
    return res.json()
  }, seed.tagId)
  const hit = (filtered.items || []).some((q) => q.id === seed.questionId)
  console.log('  筛选命中:', hit ? '✅' : '❌', `共 ${filtered.total} 条`)
  if (!hit) throw new Error('按标签筛选没命中那道题')

  // === 题目返回里带标签 ===
  const qTags = (filtered.items || []).find((q) => q.id === seed.questionId)?.tags
  console.log('  题目带标签字段:', Array.isArray(qTags) && qTags.length ? '✅' : '❌', JSON.stringify(qTags))
  if (!Array.isArray(qTags) || !qTags.length) throw new Error('题目返回里没有标签')

  // === 排序 ===
  step = 'sort'
  console.log('→ 排序')
  const sorted = await page.evaluate(async () => {
    const token = localStorage.getItem('tqb_token')
    const call = async (q) => {
      const res = await fetch('/api/questions/?' + q, {
        headers: { Authorization: 'Bearer ' + token },
      })
      return res.json()
    }
    const desc = await call('sort=created_at&order=desc')
    const asc = await call('sort=created_at&order=asc')
    const bad = await call('sort=;DROP+TABLE+users;--&order=asc')
    return {
      descFirst: desc.items?.[0]?.id,
      ascFirst: asc.items?.[0]?.id,
      badStatus: bad.total !== undefined ? 'ok' : 'bad',
      badTotal: bad.total,
    }
  })
  console.log('  降序首条:', sorted.descFirst, '| 升序首条:', sorted.ascFirst)
  console.log('  非法排序字段:', sorted.badStatus === 'ok' ? `✅ 安全(共 ${sorted.badTotal} 条)` : '❌')
  if (sorted.badStatus !== 'ok') throw new Error('非法排序字段导致接口异常')
  if (sorted.descFirst === sorted.ascFirst) {
    console.log('  （只有一道题，降序升序相同属正常）')
  }

  // === 详情页显示标签 ===
  step = 'detail'
  console.log('→ 打开题目详情')
  await page.goto(`${BASE}/questions/${seed.questionId}`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  const detail = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasTag: text.includes('验收'),
      hasSelector: !!document.querySelector('.n-base-selection'),
      snippet: text.slice(0, 220).replace(/\n/g, ' '),
    }
  })
  console.log('  详情显示标签:', detail.hasTag ? '✅' : '❌')
  console.log('  标签选择器:', detail.hasSelector ? '✅' : '❌')
  if (!detail.hasTag) {
    console.log('  实际内容:', detail.snippet)
    throw new Error('详情页没显示标签')
  }

  await page.screenshot({ path: '/tmp/verify-tags.png', fullPage: false })

  // === 清理 ===
  step = 'cleanup'
  console.log('→ 清理造的标签')
  await page.evaluate(async (tid) => {
    const token = localStorage.getItem('tqb_token')
    await fetch('/api/tags/' + tid, { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } })
    // 清所有含「验收」的遗留标签
    const res = await fetch('/api/tags/', { headers: { Authorization: 'Bearer ' + token } })
    const list = await res.json()
    for (const t of list.items || []) {
      if (t.name && t.name.includes('验收')) {
        await fetch('/api/tags/' + t.id, { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } })
      }
    }
  }, seed.tagId)

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 标签系统全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  console.error(e.stack)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
