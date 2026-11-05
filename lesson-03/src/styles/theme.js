/**
 * naive-ui 主题覆盖 —— b 阶段视觉系统
 *
 * 为什么要有这一层
 * --------------
 * naive-ui 自带一套配色（它默认的 primary 是绿色系），
 * 跟我们的设计令牌（靛蓝主色）对不上。
 * NConfigProvider 的 theme-overrides 就是用来把两套拉齐的。
 *
 * 值全部从 tokens.css 的同名变量来 —— 改令牌，组件跟着变。
 */

import { lightTheme, darkTheme } from 'naive-ui'

/** 把 CSS 变量读成 JS 值（运行时） */
function cssVar(name, fallback) {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/**
 * 生成主题覆盖
 * @param {boolean} dark - 是否深色
 */
export function buildThemeOverrides(dark = false) {
  const primary = cssVar('--tqb-primary', '#2f6fed')
  const primaryHover = cssVar('--tqb-primary-hover', '#4a83f5')
  const primaryPressed = cssVar('--tqb-primary-pressed', '#1f56c9')
  const success = cssVar('--tqb-success', '#16a34a')
  const warning = cssVar('--tqb-warning', '#d97706')
  const error = cssVar('--tqb-danger', '#dc2626')
  const info = cssVar('--tqb-info', '#0891b2')
  const textBase = cssVar('--tqb-text-primary', '#1a1d23')
  const bodyColor = cssVar('--tqb-bg-page', '#f4f6f9')
  const cardColor = cssVar('--tqb-bg-card', '#ffffff')
  const borderRadius = cssVar('--tqb-radius-md', '6px')
  const fontSize = cssVar('--tqb-font-base', '14px')

  return {
    common: {
      primaryColor: primary,
      primaryColorHover: primaryHover,
      primaryColorPressed: primaryPressed,
      primaryColorSuppl: primary,
      successColor: success,
      warningColor: warning,
      errorColor: error,
      infoColor: info,
      textColorBase: textBase,
      textColor1: textBase,
      bodyColor,
      cardColor,
      modalColor: cardColor,
      popoverColor: cardColor,
      borderRadius,
      borderRadiusSmall: cssVar('--tqb-radius-sm', '4px'),
      fontSize,
      fontFamily:
        "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Segoe UI', Roboto, sans-serif",
      // 表格
      thColor: cssVar('--tqb-bg-subtle', '#fafbfd'),
      thTextColor: cssVar('--tqb-text-secondary', '#6b7280'),
      tdColorHover: cssVar('--tqb-bg-hover', '#f7f9fc'),
      borderColor: cssVar('--tqb-border', '#e4e7ec'),
    },
    Card: {
      borderRadius: cssVar('--tqb-radius-lg', '10px'),
      color: cardColor,
      borderColor: cssVar('--tqb-border', '#e4e7ec'),
    },
    DataTable: {
      thFontWeight: '600',
      borderColor: cssVar('--tqb-border', '#e4e7ec'),
    },
    Button: {
      borderRadiusMedium: borderRadius,
      borderRadiusSmall: cssVar('--tqb-radius-sm', '4px'),
      fontWeight: '500',
    },
    Input: {
      borderRadius: borderRadius,
    },
    Select: {
      peers: {
        InternalSelection: { borderRadius: borderRadius },
      },
    },
    Tag: {
      borderRadius: cssVar('--tqb-radius-sm', '4px'),
    },
    Tree: {
      nodeHeight: '32px',
      nodeBorderRadius: borderRadius,
    },
    Dialog: {
      borderRadius: cssVar('--tqb-radius-lg', '10px'),
    },
    Menu: {
      itemBorderRadius: borderRadius,
    },
  }
}

export { lightTheme, darkTheme }
