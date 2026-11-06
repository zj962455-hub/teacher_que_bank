/**
 * 无头验证：课 34 · 灰度试用入口 + 老师反馈收集
 *
 * 验证什么
 * --------
 * 1. 登录页有「注册」页签，填邀请码能注册成功并**直接进首页**（自动登录）
 * 2. 邀请码填错时，页面显示后端给的中文原因（看得懂，不是「注册失败」）
 * 3. 顶栏「反馈」按钮弹出弹窗，能提交反馈
 * 4. /feedbacks 页面能看到自己提的反馈
 * 5. 管理员登录后导航里出现「邀请码」入口，能生成新邀请码
 * 6. 管理员在 /feedbacks 能看到别人的反馈（带用户名）并能改状态
 * 7. 全程无运行时错误（pageerror / console.error / 401-403 意外响应）
 *
 * 本轮增量（课 34 · 灰度第二版）：
 * 8. 反馈带「谁提的」：reporter 落库 + 缺省时用 display_name 兜底
 * 9. 共享账号不能改密码（界面提示 + 后端 403）
 * 10. 反馈汇总 summary 数字对 + contributors 能区分老师
 * 11. CSV 导出带 BOM + 公式注入被转义
 * 12. /guide 使用指南页能打开
 *
 * 跑法：
 *   cd lesson-03
 *   node scripts/verify-lesson34.cjs
 *
 * ⚠️ 前置：本地后端(8000) + vite dev(5173) 起着。脚本会自己备好账号：
 *   verify_admin（管理员）/ verify_shared（共享账号，禁改密）
 *   邀请码由 generate_invites 脚本生成。
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'http://localhost:5173'
const API = process.env.VERIFY_API || 'http://localhost:8000'
const ADMIN = process.env.VERIFY_ADMIN || 'verify_admin'
const SHARED = process.env.VERIFY_SHARED || 'verify_shared'
const SHARED_DISPLAY = process.env.VERIFY_SHARED_DISPLAY || '共享试用账号'
const PASS = process.env.VERIFY_PASS || 'Verify1234'
const PYTHON = '/Users/rrobot/Desktop/dev/teacher_question_bank/lesson-02/venv/bin/python'
const BACKEND = '/Users/rrobot/Desktop/dev/teacher_question_bank/lesson-02'

const errors = []
const failedRequests = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

/** 用原生 setter 赋值并触发 input 事件（Vue v-model 劫持了 value setter） */
async function fillInput(page, placeholder, value) {
  await page.evaluate(
    (ph, val) => {
      const el = [...document.querySelectorAll('input, textarea')].find(
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

/** 点一个文字完全匹配的按钮 */
async function clickButton(page, text, scope = 'document') {
  const clicked = await page.evaluate(
    (t, sc) => {
      const root = sc === 'document' ? document : document.querySelector(sc)
      if (!root) return false
      const btn = [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === t)
      if (!btn) return false
      btn.click()
      return true
    },
    text,
    scope,
  )
  if (!clicked) throw new Error(`找不到按钮「${text}」`)
}

/** 点一个文字包含关键字的元素（tab 头、链接等） */
async function clickText(page, text) {
  const clicked = await page.evaluate((t) => {
    const el = [...document.querySelectorAll('a, button, .n-tabs-tab, .n-menu-item')].find(
      (x) => x.textContent && x.textContent.trim().includes(t),
    )
    if (!el) return false
    el.click()
    return true
  }, text)
  if (!clicked) throw new Error(`找不到可点元素「${text}」`)
}

/** 准备一条邀请码（直接调后端脚本里的服务，不经过 UI） */
async function makeInvite() {
  const { execFileSync } = require('child_process')
  const out = execFileSync(
    PYTHON,
    [
      '-m', 'app.scripts.generate_invites',
      '--count', '1', '--label', '无头验证', '--max-uses', '2', '--expires-days', '30',
    ],
    { cwd: BACKEND, encoding: 'utf8' },
  )
  const code = out.match(/TQB-[A-Z0-9-]+/g)
  if (!code || !code.length) throw new Error('生成邀请码失败：' + out)
  return code[0]
}

/**
 * 备好两个账号（幂等 —— 跑多少遍都行）
 *   verify_admin  —— 管理员（能管邀请码、看全部反馈、导出）
 *   verify_shared —— 共享试用账号（allow_password_change=false）
 *
 * ⚠️ 共享账号的「禁改密」每次都强制写一遍 ——
 *    这个标记是脚本创建时定的，被人改过就会让验证失真。
 */
async function ensureUsers() {
  const { execFileSync } = require('child_process')
  const py = `
import sys
sys.path.insert(0, ${JSON.stringify(BACKEND)})
from sqlmodel import Session, select
from app.database import engine
from app.models import User
from app.scripts.create_users import hash_password

specs = [
    (${JSON.stringify(ADMIN)}, "验证管理员", True, True),
    (${JSON.stringify(SHARED)}, ${JSON.stringify(SHARED_DISPLAY)}, False, False),
]
with Session(engine) as s:
    for username, display, admin, allow_change in specs:
        u = s.exec(select(User).where(User.username == username)).first()
        if u is None:
            u = User(
                username=username, display_name=display,
                password_hash=hash_password(${JSON.stringify(PASS)}),
                must_change_password=False, is_active=True,
                is_admin=admin, allow_password_change=allow_change,
            )
            s.add(u)
            s.commit()
            s.refresh(u)
        else:
            u.display_name = display
            u.is_admin = admin
            u.allow_password_change = allow_change
            s.add(u)
            s.commit()
print("ok")
`
  const out = execFileSync(PYTHON, ['-c', py], { cwd: BACKEND, encoding: 'utf8' })
  if (!out.includes('ok')) throw new Error('准备账号失败：' + out)
}

/** 后端直连：拿 token */
async function apiLogin(username) {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password: PASS }),
  })
  if (!res.ok) throw new Error(`登录 ${username} 失败：${res.status}`)
  return (await res.json()).token
}

let failures = 0

function step(name, ok, extra = '') {
  console.log(`  ${ok ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
  if (!ok) {
    failures += 1
    process.exitCode = 1
  }
}

async function main() {
  await ensureUsers()
  const inviteCode = await makeInvite()
  console.log('→ 准备的邀请码:', inviteCode)

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    // 「Failed to load resource」是浏览器对 HTTP 4xx/5xx 的固定提示，
    // 不是运行时异常 —— 真正的 HTTP 状态由下面的 response 钩子记账。
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) {
      errors.push(`console.error: ${m.text()}`)
    }
  })
  page.on('requestfailed', (r) => {
    failedRequests.push(`${r.url()} → ${r.failure()?.errorText}`)
  })
  // HTTP 错误状态：故意制造的那几次不计
  page.on('response', (r) => {
    const url = r.url()
    const expected =
      url.includes('/api/auth/register') ||      // 错邀请码（故意）
      url.includes('/api/auth/change-password')  // 共享账号改密被拒（故意）
    if (r.status() >= 400 && !expected) {
      errors.push(`HTTP ${r.status()}: ${url}`)
    }
  })

  // === 1. 登录页有「注册」页签 ===
  console.log('→ 打开首页')
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(1500)

  const hasLoginPanel = await page.evaluate(() => !!document.querySelector('.login-panel'))
  step('未登录显示登录面板', hasLoginPanel)

  await clickText(page, '注册')
  await wait(600)
  const hasRegisterTab = await page.evaluate(() =>
    document.body.innerText.includes('邀请码') && document.body.innerText.includes('注册并进入'),
  )
  step('登录页有「注册」页签（邀请码 + 注册并进入）', hasRegisterTab)

  // === 2. 邀请码填错 → 看得懂的中文原因 ===
  console.log('→ 用错的邀请码注册（应给出中文原因）')
  await fillInput(page, '管理员发给你的邀请码', 'TQB-WRONG-CODE-XX')
  await fillInput(page, '登录用的用户名', 'verify_bad_code')
  await fillInput(page, '大写 + 小写 + 数字', 'Verify1234')
  await wait(200)
  await clickButton(page, '注册并进入')
  await wait(1500)
  const errText = await page.evaluate(() => {
    const alert = document.querySelector('.n-alert')
    return alert ? alert.innerText.trim() : ''
  })
  step('错邀请码有中文提示', errText.includes('邀请码'), JSON.stringify(errText))

  // === 3. 用真邀请码注册 → 自动登录进首页 ===
  // 用户名每次跑都要新（用户名唯一 —— 上次跑过就注册不了啦）
  const NEW_USER = `verify_new_${Date.now().toString().slice(-8)}`
  console.log('→ 用真邀请码注册（用户名', NEW_USER, '）')
  await fillInput(page, '管理员发给你的邀请码', inviteCode)
  await fillInput(page, '登录用的用户名', NEW_USER)
  await fillInput(page, '同事看到的名字', '新来的老师')
  await wait(200)
  await clickButton(page, '注册并进入')
  await wait(2500)

  const afterRegister = await page.evaluate(() => ({
    loginPanel: !!document.querySelector('.login-panel'),
    token: !!localStorage.getItem('tqb_token'),
    text: document.body.innerText.slice(0, 200),
    url: location.pathname,
  }))
  step('注册后登录面板消失', !afterRegister.loginPanel)
  step('注册后有 token（自动登录）', afterRegister.token)
  step('注册后进了首页', afterRegister.url === '/', afterRegister.url)

  // === 4. 顶栏「反馈」按钮 → 弹窗 ===
  console.log('→ 点顶栏「反馈」')
  await clickButton(page, '💬 反馈')
  await wait(800)
  const modalOpen = await page.evaluate(() => !!document.querySelector('.n-modal'))
  step('反馈弹窗打开', modalOpen)

  const contentText = '导出 PDF 时根号变成了方块，麻烦看一下'
  await fillInput(page, '张老师·市三中', '张老师·市三中')
  await fillInput(page, '微信 / 手机', '微信 zhanglaoshi')
  await fillInput(page, '例如：导出 PDF 时', contentText)
  await wait(200)
  await clickButton(page, '提交反馈')
  await wait(2000)

  const afterSubmit = await page.evaluate(() => ({
    modal: !!document.querySelector('.n-modal'),
    message: document.querySelector('.n-message')?.innerText?.trim() || '',
  }))
  step('提交后弹窗关闭', !afterSubmit.modal)
  step('提交有成功提示', afterSubmit.message.includes('反馈已提交'), JSON.stringify(afterSubmit.message))

  // === 5. /feedbacks 能看到自己的反馈 ===
  console.log('→ 打开 /feedbacks')
  const beforeFeedbacks = errors.length
  await page.goto(`${BASE}/feedbacks`, { waitUntil: 'networkidle2' })
  await wait(1500)
  const fbText = await page.evaluate(() => document.body.innerText)
  step(
    '反馈记录页看到刚提交的反馈',
    fbText.includes('导出 PDF 时根号变成了方块'),
    fbText.slice(0, 80).replace(/\n/g, ' | '),
  )
  step('反馈记录页无新增运行时错误', errors.length === beforeFeedbacks)

  // === 6. 管理员视角 ===
  console.log('→ 切到管理员账号')
  await page.evaluate(() => localStorage.clear())
  await page.goto(BASE, { waitUntil: 'networkidle2' })
  await wait(1200)
  await fillInput(page, '用户名', ADMIN)
  await fillInput(page, '密码', PASS)
  await wait(200)
  await clickButton(page, '登录')
  await wait(2500)

  const navText = await page.evaluate(() => document.body.innerText)
  step('管理员导航出现「邀请码」入口', navText.includes('邀请码'))

  console.log('→ 打开 /invites')
  const beforeInvites = errors.length
  await page.goto(`${BASE}/invites`, { waitUntil: 'networkidle2' })
  await wait(1500)
  const invitesText = await page.evaluate(() => document.body.innerText)
  step('邀请码页面渲染', invitesText.includes('邀请码管理'))
  step('邀请码页面无新增运行时错误', errors.length === beforeInvites)

  console.log('→ 生成一个邀请码')
  await fillInput(page, '给谁发的', '无头验证生成')
  await clickButton(page, '生成邀请码')
  await wait(2000)
  const afterCreate = await page.evaluate(() => document.body.innerText)
  step('新邀请码出现在列表', /TQB-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}/.test(afterCreate))

  console.log('→ 打开 /feedbacks（管理员看全部）')
  await page.goto(`${BASE}/feedbacks`, { waitUntil: 'networkidle2' })
  await wait(1500)
  const adminFbText = await page.evaluate(() => document.body.innerText)
  step('管理员能看到别人的反馈', adminFbText.includes('导出 PDF 时根号变成了方块'))
  step('管理员能看到提交人', adminFbText.includes(NEW_USER), '')
  await page.screenshot({ path: '/tmp/verify-lesson34-feedbacks.png', fullPage: false })

  // === 8. 反馈带「谁提的」 ===
  console.log('→ 校验「谁提的」（reporter / contact）')
  step('管理员视图显示 reporter', adminFbText.includes('张老师·市三中'))
  step('管理员视图显示 contact', adminFbText.includes('微信 zhanglaoshi'))

  // 兜底：reporter 不填 → 后端用 display_name 顶上
  const sharedToken = await apiLogin(SHARED)
  const fbResp = await fetch(`${API}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sharedToken}` },
    body: JSON.stringify({
      category: 'bug',
      content: '=1+1 应该等于 2，识别出来是 3',
      contact: '微信 zhanglaoshi',
    }),
  })
  const fbBody = await fbResp.json()
  step('reporter 缺省时用 display_name 兜底', fbBody.reporter === SHARED_DISPLAY, String(fbBody.reporter))
  step('contact 落库', fbBody.contact === '微信 zhanglaoshi', String(fbBody.contact))

  // === 9. 共享账号不能改密码 ===
  console.log('→ 共享账号改密（应被拒）')
  const cpResp = await fetch(`${API}/api/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sharedToken}` },
    body: JSON.stringify({ old_password: PASS, new_password: 'Other1234' }),
  })
  const cpBody = await cpResp.json()
  step('共享账号改密被拒（403）', cpResp.status === 403, String(cpResp.status))
  step('错误码 auth.password_change_locked', cpBody.code === 'auth.password_change_locked', String(cpBody.code))
  step('提示文案说清为什么', String(cpBody.detail).includes('共享试用账号'), String(cpBody.detail))

  console.log('→ 共享账号的个人中心（不显示改密表单）')
  await page.evaluate(() => localStorage.clear())
  await page.goto(BASE, { waitUntil: 'networkidle2' })
  await wait(1200)
  await fillInput(page, '用户名', SHARED)
  await fillInput(page, '密码', PASS)
  await wait(200)
  await clickButton(page, '登录')
  await wait(2500)
  await page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
  await wait(1500)
  const sharedProfileText = await page.evaluate(() => document.body.innerText)
  step('共享账号看不到改密表单', !sharedProfileText.includes('修改密码'))
  step('共享账号看到禁改密提示', sharedProfileText.includes('共享试用账号'))

  // === 10/11. 汇总 + 导出（管理员） ===
  console.log('→ 切回管理员，校验汇总与导出')
  await page.evaluate(() => localStorage.clear())
  await page.goto(BASE, { waitUntil: 'networkidle2' })
  await wait(1200)
  await fillInput(page, '用户名', ADMIN)
  await fillInput(page, '密码', PASS)
  await wait(200)
  await clickButton(page, '登录')
  await wait(2500)

  const adminToken = await apiLogin(ADMIN)
  const authH = { Authorization: `Bearer ${adminToken}` }

  const listBody = await (await fetch(`${API}/api/feedback`, { headers: authH })).json()
  const sumBody = await (await fetch(`${API}/api/feedback/summary`, { headers: authH })).json()
  step('summary 总数 = 反馈条数', sumBody.total === listBody.total, `${sumBody.total} vs ${listBody.total}`)
  const catSum = Object.values(sumBody.by_category).reduce((a, b) => a + b, 0)
  step('summary 分类分布加起来 = 总数', catSum === sumBody.total, `${catSum} vs ${sumBody.total}`)
  step('summary 有提交人聚合', Array.isArray(sumBody.contributors) && sumBody.contributors.length > 0)
  const contributors = sumBody.contributors.map((c) => c.reporter)
  step('提交人聚合里有自报身份', contributors.includes('张老师·市三中'), contributors.join(' / '))
  step('共享账号按 display_name 聚合', contributors.includes(SHARED_DISPLAY), contributors.join(' / '))

  const csvResp = await fetch(`${API}/api/feedback/export?format=csv`, { headers: authH })
  // ⚠️ 用 arrayBuffer 而不是 text() ——
  //    Response.text() 会把开头的 BOM 吃掉（WHATWG 规范如此），
  //    看不出「到底有没有带 BOM」。要看原始字节。
  const csvBytes = new Uint8Array(await csvResp.clone().arrayBuffer())
  const csvText = await csvResp.text()
  step('CSV 导出成功', csvResp.status === 200, String(csvResp.status))
  step(
    'CSV 带 BOM（Excel 打开不乱码）',
    csvBytes[0] === 0xef && csvBytes[1] === 0xbb && csvBytes[2] === 0xbf,
    [...csvBytes.slice(0, 3)].map((b) => b.toString(16)).join(' '),
  )
  step('CSV 公式注入被转义', csvText.includes("'=1+1"), csvText.split('\n').find((l) => l.includes('1+1')) || '')
  step('CSV 未裸露 = 开头的单元格', !csvText.includes(',=1+1'))

  const mdResp = await fetch(`${API}/api/feedback/export?format=markdown`, { headers: authH })
  const mdText = await mdResp.text()
  step('Markdown 导出成功', mdResp.status === 200, String(mdResp.status))
  step('Markdown 有类别分组标题', mdText.includes('## 功能异常'), mdText.split('\n')[0])
  step('Markdown 含提交人', mdText.includes('张老师·市三中'))

  // 管理员的反馈页：统计卡片 + 两个导出按钮
  console.log('→ 管理员反馈页的统计卡片与导出按钮')
  const beforeStats = errors.length
  await page.goto(`${BASE}/feedbacks`, { waitUntil: 'networkidle2' })
  await wait(1800)
  const statsText = await page.evaluate(() => document.body.innerText)
  step('反馈页有统计卡片（总数）', statsText.includes('反馈总数'))
  step('反馈页有统计卡片（待处理）', statsText.includes('待处理'))
  step('反馈页有统计卡片（已处理）', statsText.includes('已处理'))
  step('反馈页有提交人分布', statsText.includes('谁提的：'))
  step('反馈页有导出 Markdown 按钮', statsText.includes('导出 Markdown'))
  step('反馈页有导出 CSV 按钮', statsText.includes('导出 CSV'))
  step('反馈页无新增运行时错误', errors.length === beforeStats)

  // === 12. 使用指南页 ===
  console.log('→ 打开 /guide')
  const beforeGuide = errors.length
  await page.goto(`${BASE}/guide`, { waitUntil: 'networkidle2' })
  await wait(1500)
  const guideText = await page.evaluate(() => document.body.innerText)
  step('/guide 页面能打开', guideText.includes('使用指南'))
  step('/guide 写了登录步骤', guideText.includes('管理员给你的账号'))
  step('/guide 提醒共享账号不要改密码', guideText.includes('不要改密码'))
  step('/guide 提醒 OCR 要校对', guideText.includes('校对'))
  step('/guide 写了反馈怎么提', guideText.includes('反馈记录'))
  step('/guide 有常见问题', guideText.includes('常见问题'))
  step('/guide 页面无新增运行时错误', errors.length === beforeGuide)
  await page.screenshot({ path: '/tmp/verify-lesson34-guide.png', fullPage: false })

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  console.log('失败请求:', failedRequests.length ? failedRequests : '无 ✅')
  if (errors.length || failedRequests.length) process.exit(1)
  if (failures) {
    console.log(`\n❌ 有 ${failures} 项没通过`)
    process.exit(1)
  }
  console.log('\n✅ 课 34 前端验证全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
