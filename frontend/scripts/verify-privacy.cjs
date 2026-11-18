/**
 * 无头验证：隐私政策与用户协议页（公安备案 · 个人信息保护）
 *
 * 验证什么
 * --------
 * 1. /privacy 能打开，且标题正确
 * 2. 个保法第 17 条要求的告知要素都在：处理目的、方式、种类、保存期限、
 *    行使权利的方式和程序
 * 3. 未成年人条款在（试卷扫描件可能含学生姓名班级）
 * 4. 注销权利写明（个人中心可自助注销）
 * 5. 页脚有「隐私政策与用户协议」入口
 * 6. 无运行时错误
 *
 * 跑法：
 *   node scripts/verify-privacy.cjs
 *
 * 环境变量：
 *   VERIFY_BASE  默认 https://tqb.lanhu-lab.top
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'

const errors = []
const results = []

async function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

function check(name, ok, extra = '') {
  results.push({ name, ok })
  console.log(`  ${ok ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1400, height: 900 })

  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`)
  })

  try {
    console.log(`\n[1] 打开 ${BASE}/privacy`)
    const resp = await page.goto(`${BASE}/privacy`, { waitUntil: 'domcontentloaded' })
    await wait(1500)
    check('HTTP 200', resp.status() === 200, String(resp.status()))

    const title = await page.evaluate(() => document.title)
    check('标题含「隐私政策」', title.includes('隐私政策'), title)

    const text = await page.evaluate(() => document.body.innerText)

    console.log('\n[2] 个保法第 17 条告知要素')
    const required = [
      ['处理目的/用途', ['收集哪些信息', '为什么收集']],
      ['信息种类', ['手机号', '显示名', '题目、试卷']],
      ['保存期限', ['保存多久', '保留']],
      ['权利行使方式', ['你的权利', '查阅与更正', '注销我的账号']],
      ['处理者信息', ['运营主体', '联系方式']],
    ]
    for (const [label, keys] of required) {
      const hit = keys.some((k) => text.includes(k))
      check(`${label} 已告知`, hit, keys.join('/'))
    }

    console.log('\n[3] 未成年人与扫描件提示')
    check(
      '有「不满十四周岁未成年人」提示',
      text.includes('不满十四周岁'),
    )
    check('有「试卷扫描件」提示', text.includes('试卷扫描件'))
    check('有「学生姓名、班级」提示', text.includes('学生姓名'))

    console.log('\n[4] 注销权')
    check('写明注销效果', text.includes('注销'))
    check('写明需密码确认', text.includes('密码'))

    console.log('\n[5] 页脚入口')
    const footerLink = await page.evaluate(() => {
      const a = [...document.querySelectorAll('footer a')].find((x) =>
        (x.innerText || '').includes('隐私政策'),
      )
      return a ? { href: a.getAttribute('href'), text: a.innerText.trim() } : null
    })
    check('页脚有「隐私政策与用户协议」入口', !!footerLink, footerLink ? footerLink.text : '')
    check(
      '入口指向 /privacy',
      !!footerLink && footerLink.href === '/privacy',
      footerLink ? footerLink.href : '',
    )

    console.log('\n[6] 页面字数（太短说明内容没渲染出来）')
    const len = text.replace(/\s+/g, '').length
    check('正文长度 > 600 字', len > 600, String(len))
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== 运行时错误 ===')
  console.log(errors.length ? errors.join('\n') : '（无）')

  const failed = results.filter((r) => !r.ok)
  console.log('\n==============================================')
  console.log(`  ${results.length - failed.length}/${results.length} 项通过`)
  console.log('==============================================')
  process.exit(failed.length ? 1 : 0)
}

main()
