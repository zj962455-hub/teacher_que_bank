/**
 * 无头验证：章节分类管理（分类树）— lesson-11
 *
 * 验证什么
 * --------
 * 1. /categories 页能渲染出树（不是白屏），节点数正确
 * 2. 节点标签带题目统计（全部 / 本级）
 * 3. 选中节点 → 右侧「节点操作」面板出现
 * 4. 新建顶层分类 → 树里多一个节点
 * 5. 重命名 → 标签变了
 * 6. 删除 → 节点消失
 * 7. 全程无运行时错误（pageerror / console.error）
 *
 * 跑法：
 *   node scripts/verify-categories.cjs
 *   VERIFY_BASE=https://tqb.lanhu-lab.top VERIFY_USER=test1 VERIFY_PASS=abc123 node scripts/verify-categories.cjs
 *
 * ⚠️ 脚本会**自己造分类数据**再验，验完删掉 —— 不依赖环境里有没有种子数据。
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

async function treeLabels(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('.n-tree-node-content')]
      .map((n) => n.innerText.trim().replace(/\s+/g, ' '))
      .filter(Boolean),
  )
}

/**
 * 选中树里的某个节点
 * ⚠️ naive-ui NTree 重复点击**已选中**的节点会取消选中
 *    —— 所以先看右侧面板的 .node-name，对上了就别再点
 */
async function selectNode(page, name) {
  const current = await page.evaluate(() => {
    const el = document.querySelector('.node-name')
    return el ? el.innerText.trim() : null
  })
  if (current === name) return true
  await page.evaluate((tag) => {
    // ⚠️ 必须按「剥掉尾部题数后的完整名字」精确匹配
    //    用 includes 的话，「验收57257」会命中「数学验收57257 (0)」，
    //    find() 取第一个 → 选错节点。
    const strip = (t) => t.trim().replace(/\s*[（(]\d+\s*[)）]\s*$/, '').trim()
    const nodes = [...document.querySelectorAll('.n-tree-node-content')]
    const exact = nodes.find((x) => strip(x.innerText) === tag)
    const target = exact || nodes.find((x) => strip(x.innerText).includes(tag))
    if (target) target.click()
  }, name)
  await wait(700)
  const now = await page.evaluate(() => {
    const el = document.querySelector('.node-name')
    return el ? el.innerText.trim() : null
  })
  if (now !== name) throw new Error(`选中「${name}」失败（面板当前是 ${now}）`)
  return true
}


/**
 * 用 API 造一棵自己的分类树（不依赖环境的初始数据）
 *
 * 线上 test1 是空账号，旧脚本假设「本地有种子数据」，
 * 跑到生产就报「树节点数异常：0」—— 那是测试前置条件缺失，不是产品 bug。
 *
 * 造：顶层「数学」→ 子「函数」「几何」，以及一个独立顶层「物理」
 * 便于后面验「拖拽排序」「上移下移」。
 */
async function seedCategories(page, tag) {
  const result = await page.evaluate(async (t) => {
    const token = localStorage.getItem('tqb_token')
    if (!token) return { ok: false, error: '没有 token' }

    const call = async (method, path, body) => {
      const res = await fetch(path, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + token,
        },
        body: body ? JSON.stringify(body) : undefined,
      })
      return { status: res.status, data: await res.json().catch(() => null) }
    }

    const made = []
    const top = await call('POST', '/api/categories/', { name: '数学' + t })
    if (top.status !== 200) return { ok: false, error: '建顶层失败 ' + top.status }
    made.push(top.data.id)

    // ⚠️ 子分类名字也要带 tag ——
    //    删父分类时子分类是「上提」而不是跟着删（产品设计），
    //    名字不带 tag 的话 purge 清不掉，会留孤儿节点。
    for (const sub of ['函数', '几何']) {
      const r = await call('POST', '/api/categories/', { name: sub + t, parent_id: top.data.id })
      if (r.status === 200) made.push(r.data.id)
    }

    const other = await call('POST', '/api/categories/', { name: '物理' + t })
    if (other.status === 200) made.push(other.data.id)

    return { ok: true, ids: made }
  }, tag)

  if (!result.ok) throw new Error('造分类数据失败: ' + result.error)
  console.log('  已造分类:', result.ids.length, '个')
  return result.ids
}

/**
 * 清理刚造的分类（验完删掉，不留垃圾数据）
 */
async function cleanupCategories(page, ids) {
  if (!ids || !ids.length) return
  await page.evaluate(async (list) => {
    const token = localStorage.getItem('tqb_token')
    // 先删子后删父 —— 删父时子分类会上提，先删子才清得干净
    for (const id of list.slice().reverse()) {
      await fetch('/api/categories/' + id, {
        method: 'DELETE',
        headers: { Authorization: 'Bearer ' + token },
      })
    }
  }, ids)
}


/**
 * 标签精确匹配（剥掉尾部的题数）
 *
 * ⚠️ 不能用 includes！
 *   节点名里可能互相包含（如「验收84919」和「数学验收84919」），
 *   includes 会误判 → 必须剥掉题数后**全等**。
 */
function labelMatches(labels, name) {
  const strip = (t) => t.trim().replace(/\s*[（(]\d+\s*[)）]\s*$/, '').trim()
  return labels.some((l) => strip(l) === name)
}

/**
 * 清掉所有「验收」开头的测试分类
 *
 * test1 是专用测试账号，这些节点都是历次验证留下的垃圾。
 * 脚本开头/结尾各清一次 → 幂等，不污染生产数据。
 */
async function purgeTestCategories(page) {
  const n = await page.evaluate(async () => {
    const token = localStorage.getItem('tqb_token')
    if (!token) return -1
    const res = await fetch('/api/categories/flat', {
      headers: { Authorization: 'Bearer ' + token },
    })
    if (!res.ok) return -1
    const list = await res.json()
    let deleted = 0
    for (const c of list) {
      // 名字带 tag 的一律清；孤儿（父被删后上提的）靠 parent_id 也清
      if (c.name && c.name.includes('验收')) {
        const r = await fetch('/api/categories/' + c.id, {
          method: 'DELETE',
          headers: { Authorization: 'Bearer ' + token },
        })
        if (r.ok) deleted++
      }
    }
    return deleted
  })
  if (n > 0) console.log('  已清理遗留测试分类:', n, '个')
  return n
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

  // === 造自己的分类数据（不依赖环境初始状态）===
  step = 'seed'
  console.log('→ 清遗留测试数据 + 造分类数据')
  await purgeTestCategories(page)
  const seededIds = await seedCategories(page, TAG)

  // === 分类页 ===
  step = 'categories'
  console.log('→ 打开 /categories')
  await page.goto(`${BASE}/categories`, { waitUntil: 'networkidle2', timeout: 30000 })
  await wait(2000)

  // 折叠的节点要把箭头点开（naive-ui NTree 默认收起子级）
  // 注意：树若本来就是展开的，再点一次会**折叠**回去 —— 所以点完对比数量，变少就再点回来
  const countNodes = () => page.evaluate(() => document.querySelectorAll('.n-tree-node').length)
  const before = await countNodes()
  await page.evaluate(() => {
    document.querySelectorAll('.n-tree-node-switcher:not(.n-tree-node-switcher--hide)')
      .forEach((s) => s.click())
  })
  await wait(800)
  const after = await countNodes()
  if (after < before) {
    console.log(`  （树默认已展开，点击后反而收起了 ${before}→${after}，再点回来）`)
    await page.evaluate(() => {
      document.querySelectorAll('.n-tree-node-switcher:not(.n-tree-node-switcher--hide)')
        .forEach((s) => s.click())
    })
    await wait(800)
  }

  const first = await page.evaluate(() => {
    const text = document.body.innerText
    return {
      hasTitle: text.includes('章节分类管理'),
      hasPanel: text.includes('节点操作'),
      nodeCount: document.querySelectorAll('.n-tree-node').length,
      labels: [...document.querySelectorAll('.n-tree-node-content')]
        .map((n) => n.innerText.trim().replace(/\s+/g, ' ')),
      hasTotalTag: text.includes('个分类'),
      hasQTag: text.includes('已归类'),
      snippet: text.slice(0, 200).replace(/\n/g, ' '),
    }
  })

  console.log('  页面标题:', first.hasTitle ? '✅' : '❌')
  console.log('  树节点数:', first.nodeCount)
  console.log('  节点标签:', JSON.stringify(first.labels))
  console.log('  统计标签:', first.hasTotalTag && first.hasQTag ? '✅' : '❌')
  if (!first.hasTitle) {
    console.log('  实际内容:', first.snippet)
    throw new Error('分类页没渲染出「章节分类管理」标题')
  }
  if (first.nodeCount < 4) throw new Error(`树节点数异常：${first.nodeCount}（自己造了 4 个）`)

  // 统计标签带数字（题目数）
  const withCount = first.labels.filter((l) => /\(\d/.test(l))
  console.log('  带题数标签:', withCount.length, '个', JSON.stringify(withCount))
  if (!withCount.length) throw new Error('节点标签里没有题目统计')

  // === 选中节点 → 右侧面板 ===
  step = 'select'
  console.log('→ 点第一个节点')
  // 节点名从渲染结果里取（本地/生产种子名不同，不写死）
  const firstName = first.labels[0].replace(/\s*[（(]\d+\s*[)）]\s*$/, '').trim()
  await selectNode(page, firstName)
  const panel = await page.evaluate(() => {
    const text = document.body.innerText
    const btns = [...document.querySelectorAll('button')].map((b) => b.textContent.trim())
    return {
      hasOps: text.includes('节点操作'),
      hasSub: btns.includes('+ 子分类'),
      hasRename: btns.includes('重命名'),
      hasUp: btns.includes('上移'),
      hasDown: btns.includes('下移'),
      hasDelete: btns.includes('删除'),
    }
  })
  console.log('  节点操作面板:', panel.hasOps ? '✅' : '❌')
  console.log('  操作按钮:', panel.hasSub && panel.hasRename && panel.hasUp && panel.hasDown && panel.hasDelete ? '✅ 全在' : `❌ ${JSON.stringify(panel)}`)
  if (!panel.hasOps || !panel.hasSub || !panel.hasRename || !panel.hasDelete) {
    throw new Error('选中节点后右侧操作面板不完整')
  }

  // === 新建顶层分类 ===
  step = 'create'
  console.log('→ 新建顶层分类:', TAG)
  await clickByText(page, '+ 新建顶层分类')
  await wait(600)
  await fillInput(page, '新分类名字', TAG)
  await clickByText(page, '确定')
  await wait(2000)
  let labels = await treeLabels(page)
  const created = labelMatches(labels, TAG)
  console.log('  新节点出现:', created ? '✅' : '❌', JSON.stringify(labels))
  if (!created) throw new Error('新建的分类没出现在树里')

  // === 重命名 ===
  step = 'rename'
  console.log('→ 重命名')
  await selectNode(page, TAG)
  await clickByText(page, '重命名')
  await wait(600)
  await fillInput(page, '改名字', TAG + '改')
  await clickByText(page, '确定')
  await wait(2000)
  labels = await treeLabels(page)
  const renamed = labelMatches(labels, TAG + '改')
  console.log('  重命名生效:', renamed ? '✅' : '❌', JSON.stringify(labels))
  if (!renamed) throw new Error('重命名没生效')

  // === 删除 ===
  step = 'delete'
  console.log('→ 删除')
  await selectNode(page, TAG + '改')
  await clickByText(page, '删除')
  await wait(900)
  // 二次确认弹窗
  await page.evaluate(() => {
    const dlg = document.querySelector('.n-dialog')
    if (!dlg) return
    const btn = [...dlg.querySelectorAll('button')].find((b) => b.textContent.trim() === '删除')
    if (btn) btn.click()
  })
  await wait(2000)
  labels = await treeLabels(page)
  const gone = !labelMatches(labels, TAG + '改')
  console.log('  删除生效:', gone ? '✅' : '❌', JSON.stringify(labels))
  if (!gone) throw new Error('删除没生效')

  await page.screenshot({ path: '/tmp/verify-categories.png', fullPage: false })

  // === 清理自己造的数据 ===
  step = 'cleanup'
  console.log('→ 清理造的分类数据')
  await cleanupCategories(page, seededIds)
  await purgeTestCategories(page)

  await browser.close()

  console.log('\n=== 结果 ===')
  console.log('运行时错误:', errors.length ? errors : '无 ✅')
  if (errors.length) process.exit(1)
  console.log('\n✅ 分类树全部通过')
}

main().catch((e) => {
  console.error('\n❌ 验证失败:', e.message)
  console.error(e.stack)
  if (errors.length) console.error('运行时错误:', errors)
  process.exit(1)
})
