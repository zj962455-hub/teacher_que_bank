/**
 * 从 favicon.svg 生成 PNG / ICO / og 图 —— 用无头 Chrome 截图，不引入新依赖
 *
 * 跑法：
 *   cd lesson-03
 *   node scripts/gen-icons.cjs
 *
 * 为什么需要
 * ----------
 * 浏览器标签页的图标、微信分享链接的封面图，都是从站点根目录拿静态文件的。
 * 之前只有 Vite 默认的 favicon.ico（绿色闪电）+ 标题「Vite App」——
 * 老师把试卷分享链接发到班级群，微信卡片标题直接显示「Vite App」。
 */
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const ROOT = path.join(__dirname, '..')
const PUBLIC = path.join(ROOT, 'public')

const SITE_NAME = '蓝狐题库'
const SITE_DESC = '教培数学老师的私人题库 · 拍照 OCR 录题 · 一键组卷导出'

/** 把一个 SVG 或 HTML 渲染成 PNG */
async function shoot(browser, { html, width, height, out, dpr = 1 }) {
  const page = await browser.newPage()
  await page.setViewport({ width, height, deviceScaleFactor: dpr })
  await page.setContent(html, { waitUntil: 'load' })
  await page.screenshot({ path: out, type: 'png', omitBackground: false })
  await page.close()
  console.log(`  ✓ ${path.basename(out)}  ${width}x${height}`)
}

/** 把 PNG 字节包成 ICO（Vista+ 支持 ICO 内嵌 PNG） */
function pngToIco(pngFiles) {
  const count = pngFiles.length
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0) // reserved
  header.writeUInt16LE(1, 2) // type = icon
  header.writeUInt16LE(count, 4)

  const entries = []
  const datas = []
  let offset = 6 + count * 16

  for (const { size, data } of pngFiles) {
    const e = Buffer.alloc(16)
    e.writeUInt8(size >= 256 ? 0 : size, 0) // width
    e.writeUInt8(size >= 256 ? 0 : size, 1) // height
    e.writeUInt8(0, 2) // palette
    e.writeUInt8(0, 3) // reserved
    e.writeUInt16LE(1, 4) // color planes
    e.writeUInt16LE(32, 6) // bits per pixel
    e.writeUInt32LE(data.length, 8)
    e.writeUInt32LE(offset, 12)
    entries.push(e)
    datas.push(data)
    offset += data.length
  }

  return Buffer.concat([header, ...entries, ...datas])
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })

  const svg = fs.readFileSync(path.join(PUBLIC, 'favicon.svg'), 'utf-8')

  console.log('生成图标：')
  const sizes = [16, 32, 48, 180]
  const pngs = []
  for (const s of sizes) {
    const out = path.join(PUBLIC, s === 180 ? 'apple-touch-icon.png' : `favicon-${s}.png`)
    await shoot(browser, {
      html: `<body style="margin:0">${svg.replace(/width="64" height="64"/, `width="${s}" height="${s}"`)}</body>`,
      width: s,
      height: s,
      out,
    })
    pngs.push({ size: s, data: fs.readFileSync(out) })
  }

  // ICO 只放 16/32/48 三个尺寸（Windows 标签页实际就取这几个）
  const ico = pngToIco(pngs.filter((p) => p.size <= 48))
  fs.writeFileSync(path.join(PUBLIC, 'favicon.ico'), ico)
  console.log(`  ✓ favicon.ico  (${ico.length} bytes, 内含 16/32/48 PNG)`)

  // og 图（微信/QQ 分享链接卡片封面，1200x630）
  console.log('生成分享封面：')
  const og = `
  <body style="margin:0;width:1200px;height:630px;
    font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
    background:linear-gradient(135deg,#4f8cff 0%,#1d4ed8 100%);
    color:#fff;display:flex;align-items:center;justify-content:center;
    flex-direction:column;gap:18px">
    <div style="width:112px;height:112px">${svg.replace(/width="64" height="64"/, 'width="112" height="112"')}</div>
    <div style="font-size:82px;font-weight:700;letter-spacing:2px">${SITE_NAME}</div>
    <div style="font-size:30px;opacity:.92">${SITE_DESC}</div>
    <div style="margin-top:18px;font-size:24px;opacity:.72">tqb.lanhu-lab.top</div>
  </body>`
  await shoot(browser, {
    html: og,
    width: 1200,
    height: 630,
    out: path.join(PUBLIC, 'og-image.png'),
  })

  await browser.close()
  console.log('\n✅ 图标生成完毕')
}

main().catch((e) => {
  console.error('❌', e.message)
  process.exit(1)
})
