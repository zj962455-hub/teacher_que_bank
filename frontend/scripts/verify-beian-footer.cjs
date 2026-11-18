/**
 * 无头验证：公安备案公示位（页脚）
 *
 * 验证什么
 * --------
 * 1. 页脚展示网站名「蓝狐网」（与 ICP 备案 / 公安备案填的名字一致）
 * 2. 页脚展示 ICP 备案号，链接到工信部查询页
 * 3. 公安备案位：
 *    - 未拿到号（EXPECT_MPS 为空）→ 整块不渲染，页面里不能出现「公网安备」字样
 *    - 已拿到号 → 链接 href 带 code 参数、**不能出现字面量 {{ }}**、
 *      公安徽章图标真实加载（naturalWidth > 0，不是裂图）
 * 4. 全程无运行时错误
 *
 * 跑法：
 *   node scripts/verify-beian-footer.cjs
 *   EXPECT_MPS=浙公网安备33010602012345号 node scripts/verify-beian-footer.cjs
 *
 * 环境变量：
 *   VERIFY_BASE  默认 https://tqb.lanhu-lab.top
 *   EXPECT_MPS   期望出现的公安备案号；不设置 = 期望尚未公示
 */

const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.VERIFY_BASE || 'https://tqb.lanhu-lab.top'
const EXPECT_MPS = process.env.EXPECT_MPS || ''

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
    console.log(`\n[1] 打开 ${BASE}/login`)
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await wait(1500)

    const footer = await page.evaluate(() => {
      const f = document.querySelector('footer')
      if (!f) return null
      return {
        text: f.innerText,
        html: f.innerHTML,
        links: [...f.querySelectorAll('a')].map((a) => ({
          href: a.getAttribute('href'),
          prop: a.href,          // 浏览器解析后的完整 URL（中文会被百分号编码）
          text: a.innerText.trim(),
        })),
        imgs: [...f.querySelectorAll('img')].map((i) => ({
          src: i.getAttribute('src'),
          alt: i.getAttribute('alt'),
          naturalWidth: i.naturalWidth,
          naturalHeight: i.naturalHeight,
        })),
      }
    })

    if (!footer) {
      check('页脚存在', false, '找不到 <footer>')
    } else {
      console.log('\n[2] 页脚基本信息')
      check('页脚展示网站名「蓝狐网」', footer.text.includes('蓝狐网'))
      check(
        '页脚展示 ICP 备案号',
        footer.text.includes('浙ICP备2025185898号-2'),
      )

      const icpLink = footer.links.find((l) => l.text.includes('浙ICP备'))
      check('ICP 号可点击', !!icpLink, icpLink ? icpLink.href : '未找到链接')
      check(
        'ICP 链到工信部查询页',
        !!icpLink && icpLink.href.startsWith('https://beian.miit.gov.cn'),
        icpLink ? icpLink.href : '',
      )

      console.log('\n[3] 公安备案公示位')
      const mpsLink = footer.links.find((l) => l.text.includes('公网安备'))

      if (!EXPECT_MPS) {
        check('未拿到号时不渲染公安备案位', !mpsLink)
        check(
          '页面里不出现「公网安备」字样',
          !(await page.evaluate(() => document.body.innerText)).includes('公网安备'),
        )
      } else {
        check('公安备案位已渲染', !!mpsLink, mpsLink ? mpsLink.text : '未找到')
        check(
          '显示的备案号与预期一致',
          !!mpsLink && mpsLink.text.includes(EXPECT_MPS),
          mpsLink ? mpsLink.text : '',
        )
        check(
          '链接指向公安网安局查询页',
          !!mpsLink &&
            mpsLink.href.startsWith(
              'https://beian.mps.gov.cn/#/query/webSearch?code=',
            ),
          mpsLink ? mpsLink.href : '',
        )

        const expectedCode = (EXPECT_MPS.match(/\d{6,}/) || [''])[0]
        const codeInHref = decodeURIComponent(
          (mpsLink && mpsLink.href.split('code=')[1]) || '',
        )
        check(
          'code 参数只有数字部分（不是中文全称）',
          /^\d{6,}$/.test(codeInHref),
          codeInHref,
        )
        check(
          'code 参数等于备案号里的数字部分',
          !!expectedCode && codeInHref === expectedCode,
          `期望 ${expectedCode}，实际 ${codeInHref}`,
        )
        check(
          '链接里没有字面量 {{ }}（插值没渲染 = 链接是废的）',
          !!mpsLink && !mpsLink.href.includes('{{') && !mpsLink.href.includes('}}'),
          mpsLink ? mpsLink.href : '',
        )

        const icon = footer.imgs.find((i) => (i.alt || '').includes('公安备案图标'))
        check('公安备案图标存在', !!icon, icon ? icon.src : '未找到 img')
        check(
          '公安备案图标真实加载（不是裂图）',
          !!icon && icon.naturalWidth > 0,
          icon ? `naturalWidth=${icon.naturalWidth} src=${icon.src}` : '',
        )
      }

      console.log('\n[4] 页脚原始 HTML（留证）')
      console.log('  ' + footer.html.replace(/\s+/g, ' ').slice(0, 400))
    }
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
