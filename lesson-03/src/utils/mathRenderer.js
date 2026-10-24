/**
 * 数学公式渲染工具 — lesson-07
 *
 * 解决两个问题
 * ------------
 * 1. **公式从哪来？** OCR 返回的公式有两个来源：
 *    - 独立 formula block:  { type: "formula", latex: "x^{2}+2x+1" }
 *    - 文本内嵌 $...$:     { type: "text", text: "已知f(x)=$x^2+2x+1$" }
 *    → 两种都渲染（PaddleOCR 常把公式和文字混在一个 block 里）
 *
 * 2. **怎么安全地用 v-html？**
 *    KaTeX 输出的是 HTML 字符串，必须 v-html 才能显示 → 有 XSS 风险。
 *    三道防线：
 *    - `trust: false`（默认）禁用 \href \url \includegraphics 等危险命令
 *    - `strict: "error"` 遇到未知命令直接抛错，不静默输出
 *    - `throwOnError: false` 让单个公式出错时降级显示原文，而不是整段炸掉
 *
 * 公式语法约定
 * ------------
 * - 行内公式：`$...$`（单个 $ 包裹）
 * - 块级公式：`$$...$$`（双 $ 包裹，独占一行）
 * 两者都支持。
 */

import katex from 'katex'

/**
 * KaTeX 渲染选项
 * --------------
 * throwOnError: false
 *   → 公式语法错时不抛异常，返回一段带错误标记的 HTML，
 *     配合下面的降级逻辑显示原始代码
 * strict: "error"
 *   → 未知命令直接报错（而不是静默渲染成红色文字）
 * trust: false
 *   → 默认值，禁用 \href \url \includegraphics 等有安全风险的命令
 * displayMode
 *   → 由调用方决定是行内还是块级
 * macros
 *   → 常用数学宏，减少老师手写 \times \cdot 的负担
 */
const KATEX_OPTIONS = {
  throwOnError: false,
  strict: 'error',
  trust: false,
  macros: {
    '\\R': '\\mathbb{R}',
    '\\N': '\\mathbb{N}',
    '\\Z': '\\mathbb{Z}',
    '\\degree': '^\\circ',
    '\\celsius': '^\\circ C',
  },
}

/** 渲染失败时的占位样式（黄色底 + 保留原文） */
const ERROR_STYLE = 'background:#fffbe6;border:1px solid #ffe08a;border-radius:3px;padding:0 3px;color:#874d00;'

/**
 * 渲染单个 LaTeX 公式
 *
 * @param {string} latex - LaTeX 源码（不带 $ 分隔符）
 * @param {boolean} displayMode - 是否块级显示（独立成行居中）
 * @returns {string} HTML 字符串（可直接 v-html）
 */
export function renderLatex(latex, displayMode = false) {
  if (!latex || !latex.trim()) return ''

  try {
    return katex.renderToString(latex, {
      ...KATEX_OPTIONS,
      displayMode,
    })
  } catch (e) {
    // strict:"error" 才会走到这里（throwOnError:false 时多数错误被 KaTeX 内部处理）
    return `<code style="${ERROR_STYLE}" title="LaTeX 渲染失败: ${escapeHtml(e.message)}">${escapeHtml(latex)}</code>`
  }
}

/**
 * 转义 HTML 特殊字符
 * 渲染失败时把原始 LaTeX 显示出来，必须先转义，
 * 否则 LaTeX 里的 < > & 会被当成 HTML 标签
 */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 混排渲染：文本里嵌 $...$ / $$...$$ 公式
 *
 * 为什么要自己扫 $ 而不是用正则？
 * ----------------------------------
 * 正则 /\$([^$]+)\$/g 有两个问题：
 * 1. 遇到多个公式时贪婪/惰性匹配容易错位
 * 2. 转义的 \$ 和数学里的美元符号会误判
 *
 * 用逐字符扫描能精确配对，且能识别 $$ 块级公式。
 *
 * @param {string} text - 混排文本
 * @returns {string} HTML 字符串
 */
export function renderMathText(text) {
  if (!text) return ''

  let html = ''
  let buffer = ''          // 当前累积的普通文本
  let i = 0

  while (i < text.length) {
    const ch = text[i]

    if (ch === '\\' && text[i + 1] === '$') {
      // 转义的 \$ → 当普通字符
      buffer += '$'
      i += 2
      continue
    }

    if (ch !== '$') {
      buffer += ch
      i++
      continue
    }

    // 遇到 $ —— 判断是块级 $$ 还是行内 $
    const isDisplay = text[i + 1] === '$'
    const delimiter = isDisplay ? '$$' : '$'
    const start = i + delimiter.length

    // 找配对的结束分隔符
    const end = text.indexOf(delimiter, start)
    if (end === -1) {
      // 没配对 → 当普通字符处理
      buffer += ch
      i++
      continue
    }

    const latex = text.slice(start, end)

    // 公式内容为空（$$ 或 $$$$）→ 当普通字符
    if (!latex.trim()) {
      buffer += ch
      i++
      continue
    }

    // 冲刷累积的普通文本
    if (buffer) {
      html += escapeHtml(buffer)
      buffer = ''
    }

    html += renderLatex(latex, isDisplay)
    i = end + delimiter.length
  }

  // 收尾
  if (buffer) html += escapeHtml(buffer)

  return html
}

/**
 * 渲染一个 OCR block
 *
 * 两种情况：
 * - type=formula → 整块就是公式，块级渲染
 * - type=text    → 文本里可能嵌 $...$，走混排渲染
 * - type=table   → HTML 表格，原样返回（KaTeX 不参与）
 *
 * @param {object} block - OCR block
 * @returns {string} HTML 字符串
 */
export function renderBlock(block) {
  if (!block) return ''

  if (block.type === 'formula') {
    return renderLatex(block.latex, true)
  }

  if (block.type === 'text') {
    return renderMathText(block.text || '')
  }

  if (block.type === 'table') {
    // 表格的 html 来自 PaddleOCR，不含公式，直接返回
    return block.html || ''
  }

  return escapeHtml(block.text || '')
}

/**
 * 把一组 block 拼成一段 HTML
 * 块与块之间用 <div> 分隔（保持块级结构）
 *
 * @param {Array} blocks - OCR blocks
 * @returns {string} HTML 字符串
 */
export function renderBlocks(blocks) {
  if (!blocks?.length) return ''
  return blocks.map(renderBlock).join('<div style="margin: 4px 0;"></div>')
}

/**
 * 提取纯文本（去掉公式标记）—— 用于复制到剪贴板
 * 老师复制到 Word/文档里时，$...$ 标记是噪音
 *
 * @param {string} text - 混排文本
 * @returns {string} 去掉公式标记的纯文本
 */
export function stripMathMarkers(text) {
  if (!text) return ''
  return text.replace(/\$\$?([^$]+)\$\$?/g, '$1')
}
