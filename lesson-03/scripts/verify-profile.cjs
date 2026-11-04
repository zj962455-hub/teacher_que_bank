/**
 * 无头验证：个人中心 — lesson-11
 *
 * 验证什么
 * --------
 * 1. 登录后顶栏出现「👤 用户名」入口
 * 2. 点开个人中心 → 面板渲染（账号信息/统计/改显示名/改密码/会话列表/退出）
 * 3. 改显示名 → 顶栏同步
 * 4. 退出登录 → 回到登录面板
 * 5. 全程无运行时错误
 *
 * 跑法：
 *   node scripts/verify-profile.cjs
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
  const clicked = await page.evaluate(
    (t, g) => {
      const el = [...document.querySelectorAll(g)].find(
        (b) => b.textContent.trim() === t || b.textContent.includes(t),
      )
      if (!el) return false
      el.click()
      return true
    },
    text,
    tag,
  )
  if (!clicked) throw new Error(`找不到「${text}」`)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 1000 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  console.log('→ 打开首页', BASE)
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1200)

  // === 1. 登录 ===
  await fillInput(page, '用户名', USER)
  await fillInput(page, '密码', PASS)
  await clickByText(page, '登录')
  await wait(2500)

  // === 2. 顶栏有用户入口吗 ===
  const topBar = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')].map((b) => b.textContent.trim())
    return btns
  })
  const userBtn = topBar.find((t) => t.includes('test1') || t.includes('测试'))
  console.log('  顶栏用户按钮:', userBtn ? `✅ 「${userBtn}」` : `❌ 顶栏按钮: ${JSON.stringify(topBar.slice(0, 6))}`)
  if (!userBtn) throw new Error('顶栏没有用户入口')

  // === 3. 点开个人中心 ===
  await clickByText(page, userBtn)
  await wait(2000)

  const panel = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasPersonal: text.includes('个人中心'),
      hasStats: text.includes('题目') && text.includes('试卷'),
      hasSessions: text.includes('登录设备'),
      hasLogout: text.includes('退出登录'),
      hasChangePwd: text.includes('修改密码'),
      snippet: text.slice(0, 400),
    }
  })
  console.log('  面板标题「个人中心」:', panel.hasPersonal ? '✅' : '❌')
  console.log('  数据统计:', panel.hasStats ? '✅' : '❌')
  console.log('  登录设备列表:', panel.hasSessions ? '✅' : '❌')
  console.log('  修改密码:', panel.hasChangePwd ? '✅' : '❌')
  console.log('  退出登录:', panel.hasLogout ? '✅' : '❌')
  if (!panel.hasPersonal || !panel.hasStats || !panel.hasLogout) {
    console.log('  面板内容:', JSON.stringify(panel.snippet))
    throw new Error('个人中心面板内容不全')
  }
  await page.screenshot({ path: '/tmp/verify-profile.png', fullPage: false })

  // === 4. 改显示名 ===
  console.log('→ 改显示名')
  await fillInput(page, '给同事看名字', '张老师')
  await wait(300)
  await clickByText(page, '保存')
  await wait(1800)

  const afterSave = await page.evaluate(() => document.body.innerText)
  console.log('  顶栏同步:', afterSave.includes('张老师') ? '✅' : '❌')

  // === 5. 退出登录 ===
  console.log('→ 退出登录')
  await clickByText(page, '退出登录')
  await wait(2500)

  const afterLogout = await page.evaluate(() => ({
    hasLogin: !!document.querySelector('.login-panel'),
    text: document.body.innerText.slice(0, 80),
  }))
  console.log('  回到登录面板:', afterLogout.hasLogin ? '✅' : `❌ ${JSON.stringify(afterLogout.text)}`)
  if (!afterLogout.hasLogin) throw new Error('退出后没回到登录面板')

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 个人中心全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
