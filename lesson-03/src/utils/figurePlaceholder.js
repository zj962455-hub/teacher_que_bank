/**
 * 题图占位符 —— 【题图】
 *
 * 为什么有这个占位符
 * ------------------
 * OCR 的图形块没有对应文字，纯文本/Markdown 里那块会凭空消失 ——
 * 留个【题图】占位，老师复制到 Word 时才知道「这里本来有张图」。
 *
 * 为什么要去掉
 * --------------
 * 卷子上明明有图（图是单独带进去的），正文里再写一遍【题图】就是噪音。
 * 所以**页面展示和导出都去掉**，只把占位符留在存储层 ——
 * 老师可以在题目编辑器里手动删掉它（删了就永久没了）。
 *
 * 后端同名函数：app/services/classifier.py → strip_figure_placeholder()
 */

export const FIGURE_PLACEHOLDER = '【题图】'

/**
 * 去掉正文里的【题图】占位符
 * - 整行只有占位符 → 整行丢掉
 * - 同一行里混着别的文字 → 只去掉占位符，保留这行
 * - 删完可能留下连续空行 → 收一下
 *
 * @param {string} text - 正文（Markdown 或纯文本）
 * @returns {string} 去掉占位符后的正文
 */
export function stripFigurePlaceholder(text) {
  if (!text) return ''
  const kept = []
  for (const line of String(text).split('\n')) {
    if (!line.includes(FIGURE_PLACEHOLDER)) {
      kept.push(line)
      continue
    }
    const rest = line.split(FIGURE_PLACEHOLDER).join('')
    if (rest.trim()) kept.push(rest)
  }
  return kept.join('\n').replace(/\n{3,}/g, '\n\n')
}

export default { FIGURE_PLACEHOLDER, stripFigurePlaceholder }
