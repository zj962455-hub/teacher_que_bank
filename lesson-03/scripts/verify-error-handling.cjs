/**
 * 无头验证：错误处理 + Loading 状态（课 32）
 *
 * 验证什么
 * --------
 * 1. 后端 500 → 页面显示**人话** + 「重试」按钮 + 错误编号（不是白屏）
 * 2. 网络层失败（连不上后端）→ 显示网络类文案，不是「Network Error」
 * 3. 慢响应 → 页面有 loading 反馈
 * 4. 点「重试」→ 能重新拉起来
 *
 * 怎么造错
 * --------
 * 用 puppeteer 的 request interception 把某个接口打挂：
 * - `/api/papers/` 返 500 → 试卷列表页应显示错误块
 * - 直接 abort → 模拟网络断了
 *
 * ⚠️ 全部用 `waitUntil: 'domcontentloaded'` 而不是 `networkidle2` ——
 *    被 abort 的请求会让 networkidle2 永远等不到「网络空闲」→ goto 挂到超时。
 *
 * 跑法：
 *   node scripts/verify-error-handling.cjs
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

/**
 * 让某个接口挂掉
 *
 * @param {string} mode 'error' → 返 500；'abort' → 模拟断网；'slow' → 延迟 3 秒
 */
async function breakEndpoint(page, pattern, mode = 'error') {
  await page.setRequestInterception(true)
  const handler = async (req) => {
    if (req.url().includes(pattern)) {
      if (mode === 'abort') {
        req.abort('failed').catch(() => {})
        return
      }
      if (mode === 'slow') {
        await wait(3000)
        req.continue().catch(() => {})
        return
      }
      req.respond({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: '模拟的服务器错误',
          code: 'server.internal',
          request_id: 'testreqid001',
        }),
      }).catch(() => {})
      return
    }
    req.continue().catch(() => {})
  }
  page.on('request', handler)
  return handler
}

async function unbreak(page, handler) {
  page.off('request', handler)
  await page.setRequestInterception(false)
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
    // 模拟错误时后端返回的 500 / abort 会在控制台留痕 —— 那是**预期**的
    if (m.type() === 'error' && !m.location().url.includes('/api/')) {
      errors.push(`console.error: ${m.text()}`)
    }
  })

  console.log('→ 登录')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(1500)
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(3000)

  // ---------- 场景 1：后端 500 ----------
  console.log('→ 场景 1：把 /api/papers/ 打成 500')
  const h1 = await breakEndpoint(page, '/api/papers/')
  await page.goto(`${BASE}/papers`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(3000)

  const s1 = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasErrorBlock: text.includes('重试'),
      hasDetail: text.includes('模拟的服务器错误'),
      hasRequestId: /错误编号\s*\S+/.test(text),
      snippet: text.slice(0, 220).replace(/\n/g, ' '),
    }
  })
  console.log('  错误块(含重试按钮):', s1.hasErrorBlock ? '✅' : '❌')
  console.log('  显示后端 detail:', s1.hasDetail ? '✅' : '❌')
  console.log('  显示错误编号:', s1.hasRequestId ? '✅' : '❌')
  if (!s1.hasErrorBlock) {
    console.log('  实际内容:', s1.snippet)
    throw new Error('500 时没有显示错误块（应该是一片白屏）')
  }
  if (!s1.hasRequestId) {
    console.log('  实际内容:', s1.snippet)
    throw new Error('错误块里没有 request_id（排查不了）')
  }

  // ---------- 场景 2：点重试能恢复 ----------
  console.log('→ 场景 2：解除故障后点「重试」')
  await unbreak(page, h1)
  await clickByText(page, '重试')
  await wait(3000)
  const s2 = await page.evaluate(() => document.body.innerText)
  const recovered = !s2.includes('模拟的服务器错误')
  console.log('  重试后错误消失:', recovered ? '✅' : '❌')
  if (!recovered) throw new Error('点重试没恢复')

  // ---------- 场景 3：网络断了 ----------
  console.log('→ 场景 3：把 /api/papers/ 直接 abort（模拟断网）')
  const h3 = await breakEndpoint(page, '/api/papers/', 'abort')
  await page.goto(`${BASE}/papers`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(3500)
  const s3 = await page.evaluate(() => document.body.innerText)
  const netMsg =
    s3.includes('连不上服务器') || s3.includes('检查网络') || s3.includes('网络')
  console.log('  显示网络类文案:', netMsg ? '✅' : '❌')
  console.log('  没出现 Network Error 原文:', !s3.includes('Network Error') ? '✅' : '❌')
  if (!netMsg) {
    console.log('  实际内容:', s3.slice(0, 220).replace(/\n/g, ' '))
    throw new Error('断网时没有显示网络类文案')
  }
  await unbreak(page, h3)

  // ---------- 场景 4：加载中有反馈 ----------
  console.log('→ 场景 4：慢响应时页面有 loading 反馈')
  const h4 = await breakEndpoint(page, '/api/papers/', 'slow')
  await page.goto(`${BASE}/papers`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await wait(1200)
  const s4 = await page.evaluate(() => {
    const text = document.body.innerText
    const spin = document.querySelector('.n-spin, .n-spin-body')
    return {
      hasSpin: !!spin,
      hasLoadingText: text.includes('加载中'),
      snippet: text.slice(0, 160).replace(/\n/g, ' '),
    }
  })
  console.log('  有 spinner:', s4.hasSpin ? '✅' : '❌')
  console.log('  有「加载中」文案:', s4.hasLoadingText ? '✅' : '❌')
  await unbreak(page, h4)
  if (!s4.hasSpin && !s4.hasLoadingText) {
    console.log('  实际内容:', s4.snippet)
    throw new Error('慢响应时没有任何 loading 反馈')
  }
  await wait(4000)

  await page.screenshot({ path: '/tmp/verify-error-handling.png', fullPage: false })
  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 错误处理 + Loading 状态全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
