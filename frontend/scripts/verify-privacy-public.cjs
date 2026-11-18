/**
 * 无头验证：隐私政策页**公开展示**的内容
 *
 * 为什么要有这个脚本
 * ------------------
 * 2026-11-19 实测踩到：隐私政策页把样例文字直接渲染在了公网上 ——
 * 访客（以及公安审核员）一点就看见「运营主体：（…）」这种半成品，
 * 看起来像备案材料根本没填 —— 这是实打实的备案负分。
 *
 * 只在源码层挡不够：样例文字可能从任何地方漏进来。
 * 所以直接验**访客真实看到的文字**。
 *
 * 跑法：
 *   node scripts/verify-privacy-public.cjs
 *
 * 环境变量：
 *   VERIFY_BASE      默认 https://tqb.lanhu-lab.top
 *   EXPECT_OPERATOR 期望出现的运营主体全称（不设置 = 期望不出现这一行）
 *   EXPECT_CONTACT   期望出现的应急联系方式（不设置 = 期望不出现这一行）
 *   EXPECT_MPS       期望出现的公安备案号（不设置 = 期望不出现这一行）
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const EXPECT_OPERATOR = process.env.EXPECT_OPERATOR || ''
const EXPECT_CONTACT = process.env.EXPECT_CONTACT || ''
const EXPECT_MPS = process.env.EXPECT_MPS || ''

const errors = []
const results = []

async function wait(ms) { return new Promise((r) => setTimeout(r, ms)) }

function check(name, ok, extra) {
  results.push({ name, ok })
  console.log('  ' + (ok ? '✅' : '❌') + ' ' + name + (extra ? ' — ' + extra : ''))
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1400, height: 1000 })

  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push('console.error: ' + m.text())
  })

  try {
    console.log('[1] 打开 ' + BASE + '/privacy')
    await page.goto(BASE + '/privacy', { waitUntil: 'domcontentloaded' })
    await wait(2000)

    const text = await page.evaluate(() => document.body.innerText)

    console.log('\n[2] 访客可见文本体检')
    check('页面正文有内容', text.length > 500, '长度 ' + text.length)
    const bad = ['待填', '某某', '占位', '取得后在页脚公示']
    bad.forEach((w) => {
      check('正文不含「' + w + '」', text.indexOf(w) < 0)
    })

    console.log('\n[3] 主体信息行')
    if (EXPECT_OPERATOR) {
      check('显示运营主体', text.indexOf('运营主体：' + EXPECT_OPERATOR) >= 0, EXPECT_OPERATOR)
    } else {
      check('未填主体时不出现「运营主体：」行', text.indexOf('运营主体：') < 0)
    }
    if (EXPECT_CONTACT) {
      check('显示联系方式', text.indexOf('联系方式：' + EXPECT_CONTACT) >= 0, EXPECT_CONTACT)
    } else {
      check('未填联系方式时不出现「联系方式：」行', text.indexOf('联系方式：') < 0)
    }

    console.log('\n[4] 备案号')
    check('显示 ICP 备案号', text.indexOf('浙ICP备2025185898号-2') >= 0)
    if (EXPECT_MPS) {
      check('显示公安备案号', text.indexOf('公安备案号：' + EXPECT_MPS) >= 0, EXPECT_MPS)
    } else {
      check('未取得备案号时不出现「公安备案号：」行', text.indexOf('公安备案号：') < 0)
    }

    console.log('\n[5] 相关行留证')
    text
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean)
      .filter((x) => x.indexOf('备案') >= 0 || x.indexOf('主体') >= 0 || x.indexOf('联系方式') >= 0)
      .forEach((l) => console.log('   | ' + l))
  } catch (e) {
    check('流程异常', false, e.message)
  } finally {
    await browser.close()
  }

  console.log('\n=== 运行时错误 ===')
  console.log(errors.length ? errors.join('\n') : '（无）')

  const failed = results.filter((r) => !r.ok)
  console.log('\n==============================================')
  console.log('  ' + (results.length - failed.length) + '/' + results.length + ' 项通过')
  console.log('==============================================')
  process.exit(failed.length ? 1 : 0)
}

main()
