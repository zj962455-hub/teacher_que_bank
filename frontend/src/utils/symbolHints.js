/**
 * 符号疑点检测 —— lesson-35
 *
 * 为什么只「提示」不自动改
 * ----------------------
 * 平行符号 ∥ 被识别成 '/'（PE/OA）这种情况，靠正则猜有误伤风险
 * （"A/B" 可能就是分数）。老师要求：先提示，老师确认或一键改。
 * 所以这里只负责「找出可疑的地方」+「给出改法」，自己不改数据。
 */

/** 平行符号疑点：PE/OA → PE∥OA */
const PARALLEL_RE = /([A-Z]{1,3})\s*\/\s*([A-Z]{1,3})/g

/** 角符号误识别：ZAOB → ∠AOB（Z/L 紧跟 2~3 个大写字母） */
const ANGLE_RE = /(?<![A-Za-z0-9])[ZL](?=[A-E]{2,3}(?![A-Za-z0-9]))/g

/**
 * 找出 block 里的符号疑点
 * @returns {Array<{kind, match, replacement, label, detail}>}
 */
export function detectSymbolHints(block) {
  const hints = []
  if (!block) return hints
  const isFormula = block.type === 'formula'
  const src = isFormula ? (block.latex || '') : (block.text || '')
  if (!src) return hints

  let m
  PARALLEL_RE.lastIndex = 0
  while ((m = PARALLEL_RE.exec(src))) {
    hints.push({
      kind: 'parallel',
      match: m[0],
      // 公式块用 LaTeX 命令，文本块用 unicode 符号
      replacement: isFormula
        ? m[1] + '\\parallel ' + m[2]
        : m[1] + '∥' + m[2],
      label: '疑似平行符号',
      detail: m[1] + ' ∥ ' + m[2],
    })
  }

  ANGLE_RE.lastIndex = 0
  while ((m = ANGLE_RE.exec(src))) {
    hints.push({
      kind: 'angle',
      match: m[0],
      replacement: isFormula ? '\\angle ' : '∠',
      label: '疑似角符号',
      detail: '∠' + src.slice(m.index + 1),
    })
  }

  return hints
}

/**
 * 应用一个疑点修改 → 返回新的 block（不修改原对象）
 */
export function applySymbolHint(block, hint) {
  if (!block || !hint) return block
  const isFormula = block.type === 'formula'
  const src = isFormula ? (block.latex || '') : (block.text || '')
  const next = src.replace(hint.match, hint.replacement)
  if (next === src) return block
  const out = { ...block }
  if (isFormula) {
    out.latex = next
    out.plain = next
  } else {
    out.text = next
  }
  return out
}
