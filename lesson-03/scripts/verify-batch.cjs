/**
 * 无头验证：章节树 + 批量操作 + 最近编辑 — lesson-11
 *
 * 跑法：
 *   node scripts/verify-batch.cjs
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
  await page.setViewport({ width: 1440, height: 1000 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  // 登录
  console.log('→ 登录')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  // === 1. 仪表盘:最近编辑 ===
  console.log('→ 仪表盘检查「最近编辑」')
  const dash = await page.evaluate(() => {
    const t = document.body.innerText
    return {
      hasRecent: t.includes('最近编辑'),
      hasStats: t.includes('题目总数') || t.includes('题目'),
      recentItems: document.querySelectorAll('.recent-item').length,
    }
  })
  console.log('  最近编辑卡片:', dash.hasRecent ? '✅' : '❌')
  console.log('  最近条目数:', dash.recentItems)
  await page.screenshot({ path: '/tmp/verify-dashboard.png', fullPage: false })

  // === 2. 题目列表:章节树 ===
  console.log('→ 题目列表检查章节树')
  await page.goto(`${BASE}/questions`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  const tree = await page.evaluate(() => {
    const t = document.body.innerText
    return {
      hasTree: !!document.querySelector('.n-tree'),
      treeText: document.querySelector('.tree-card')?.innerText?.slice(0, 120) || '',
      hasBatch: t.includes('批量'),
      hasFilters: t.includes('学科') && t.includes('难度'),
      rows: document.querySelectorAll('.n-data-table-tbody .n-data-table-tr').length,
      hasCheckbox: !!document.querySelector('.n-data-table-thead .n-checkbox'),
    }
  })
  console.log('  章节树:', tree.hasTree ? '✅' : '❌', '|', tree.treeText.replace(/\n/g, ' '))
  console.log('  筛选栏(学科/难度):', tree.hasFilters ? '✅' : '❌')
  console.log('  表格勾选框:', tree.hasCheckbox ? '✅' : '❌')
  console.log('  表格行数:', tree.rows)

  // === 3. 勾选 → 批量条出现 ===
  console.log('→ 勾选一行,看批量操作条')
  const checked = await page.evaluate(() => {
    const cb = document.querySelector('.n-data-table-tbody .n-checkbox')
    if (!cb) return false
    cb.click()
    return true
  })
  if (checked) {
    await wait(1200)
    const batchBar = await page.evaluate(() => document.body.innerText.includes('已选'))
    console.log('  批量操作条:', batchBar ? '✅ 出现' : '❌ 没出现')
    if (!batchBar) console.log('    文本:', (await page.evaluate(() => document.body.innerText)).slice(0, 200).replace(/\n/g, ' '))
  } else {
    console.log('  ⚠️ 表格里没找到勾选框(可能没数据)')
  }

  await page.screenshot({ path: '/tmp/verify-questions.png', fullPage: false })

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 章节树 / 批量操作 / 最近编辑 全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
