/**
 * 题目自动分类器 — lesson-06 任务 5C
 *
 * 设计目标
 * --------
 * 从 OCR 识别出的题目文本里猜出「学科 / 题型 / 年级段 / 难度」，
 * 让老师不用手填就能开始整理题目。
 *
 * 为什么用规则而不是调 LLM
 * -----------------------
 * 1. **零成本、零延迟、离线可用** —— 不消耗 API 额度，不依赖网络
 * 2. **确定性强** —— 同一道题每次分类结果一样，方便复现和调试
 * 3. **教培数学题型有限** —— 方程/几何/函数/概率就那么几类，关键词足够覆盖
 * 4. **可解释** —— 命中了哪个规则一目了然，出错好排查
 *
 * 将来如果规则覆盖不了（比如手写应用题题干太短），可以平滑替换成 LLM 调用：
 * 只要保持 classify(text) -> result 这个函数签名不变，上层组件不用改。
 *
 * 局限
 * ----
 * - 纯图形题（题干只有一张图没文字）→ 无法分类，返回「未知」
 * - 跨章节的复合题 → 只取第一个命中的分类
 */

/**
 * 学科分类规则（按优先级从上到下，命中即返回）
 *
 * ⚠️ 顺序很重要：越具体的学科排前面
 * ------------------------------------
 * 第一版把数学排第一，关键词里有'求'/'已知' 这种泛词，
 * 导致「一个物体质量2kg，求加速度」被误判成数学（因为先命中'求'）。
 *
 * 修正原则：
 * 1. **特征性强的词**（摩尔/化学式/加速度/密度）优先
 * 2. **泛词**（求/已知/证明）放到最后，只在没命中其他学科时兜底
 */
const SUBJECT_RULES = [
  // 物理：特征词很独特，放最前
  { subject: '物理', keywords: ['加速度', '电流', '电压', '电阻', '功率', '密度', '摩擦力', '浮力', '压强', '波长'] },
  // 化学：特征词同样独特
  { subject: '化学', keywords: ['摩尔', '化学式', '溶液', '浓度', '原子', '分子', '化合价', '电解质'] },
  // 生物
  { subject: '生物', keywords: ['细胞', '基因', '遗传', '光合作用', '呼吸作用', '蛋白质', '染色体'] },
  // 数学：泛词放最后兜底
  { subject: '数学', keywords: ['方程', '函数', '几何', '三角', '概率', '统计', '数列', '不等式', '证明', '已知', '求'] },
]

/** 题型分类规则（同样：特征强的排前面） */
const TYPE_RULES = [
  { type: '选择题', keywords: ['下列', '正确的是', '错误的是', '不符合', '选项', '以上都对'] },
  { type: '证明题', keywords: ['证明', '求证', '证：'] },
  { type: '计算题', keywords: ['解方程', '解不等式', '化简', '求值', '计算', '求解'] },
  { type: '填空题', keywords: ['填空', '横线上', '____', '＿＿', '…'] },
  // 应用题特征最泛，放最后兜底
  { type: '应用题', keywords: ['某', '一共', '剩下', '平均', '买', '卖出', '走了', '多少'] },
]

/** 年级段关键词（粗粒度，教学阶段） */
const GRADE_RULES = [
  { grade: '初中', keywords: ['一元二次', '勾股', '全等', '相似', '一次函数', '反比例', '圆'] },
  { grade: '高中', keywords: ['导数', '数列', '三角函数', '向量', '抛物线', '椭圆', '双曲线', '排列组合', '概率分布'] },
]

/**
 * 从文本里找第一个命中的分类
 * @param {string} text - 待分类的题目文本
 * @param {Array} rules - 规则数组 [{ 字段名: 值, keywords: [...] }]
 * @param {string} fallback - 没命中时的返回值
 */
function matchFirst(text, rules, fallback = '未知') {
  for (const rule of rules) {
    const hit = rule.keywords.some(kw => text.includes(kw))
    if (hit) return rule.subject || rule.type || rule.grade
  }
  return fallback
}

/**
 * 难度估算
 * ----------
 * MVP 阶段用「文本特征」粗判，不做真正的难度评估：
 * - 文字越长、公式越多 → 题面越复杂 → 难度越高
 * - 只有一句话 → 基础题
 *
 * 这是启发式规则，准确率有限，但对"先分个类再人工调"的场景够用。
 */
function estimateDifficulty(text, blocks = []) {
  const length = text.length
  const formulaCount = blocks.filter(b => b.type === 'formula').length
  const tableCount = blocks.filter(b => b.type === 'table').length

  // 加权打分
  let score = 0
  score += Math.min(length / 50, 3)        // 每 50 字加 1 分，上限 3
  score += formulaCount * 1.5               // 每个公式 1.5 分
  score += tableCount * 2                   // 每个表格 2 分

  if (score >= 5) return '困难'
  if (score >= 2.5) return '中等'
  return '简单'
}

/**
 * 主函数：分类一道题
 *
 * @param {string} text - 拼接后的纯文本（通常是 plainText）
 * @param {Array} blocks - OCR blocks 数组（可选，用于难度估算和公式统计）
 * @returns {{subject, type, grade, difficulty, confidence, matched}} 
 *   - subject: 学科
 *   - type: 题型
 *   - grade: 年级段
 *   - difficulty: 难度
 *   - confidence: 置信度 0~1（有无命中关键词）
 *   - matched: 命中的关键词列表（用于前端展示"为什么这么分"）
 */
export function classify(text = '', blocks = []) {
  const content = text || ''

  // 收集所有命中的关键词，方便前端解释
  const matched = []

  // 学科
  let subject = '未知'
  for (const rule of SUBJECT_RULES) {
    const kw = rule.keywords.find(k => content.includes(k))
    if (kw) {
      subject = rule.subject
      matched.push(`${rule.subject}:${kw}`)
      break
    }
  }

  // 题型
  let type = '未知'
  for (const rule of TYPE_RULES) {
    const kw = rule.keywords.find(k => content.includes(k))
    if (kw) {
      type = rule.type
      matched.push(`${rule.type}:${kw}`)
      break
    }
  }

  // 年级段
  let grade = '通用'
  for (const rule of GRADE_RULES) {
    const kw = rule.keywords.find(k => content.includes(k))
    if (kw) {
      grade = rule.grade
      matched.push(`${rule.grade}:${kw}`)
      break
    }
  }

  // 难度
  const difficulty = estimateDifficulty(content, blocks)

  // 置信度：命中几个维度 / 总共 3 个（学科、题型、年级）
  const hitCount = [subject !== '未知', type !== '未知', grade !== '通用'].filter(Boolean).length
  const confidence = Math.round((hitCount / 3) * 100) / 100

  return {
    subject,
    type,
    grade,
    difficulty,
    confidence,
    matched,
  }
}

/** 供 UI 下拉框用的选项列表 */
export const SUBJECT_OPTIONS = [
  '数学', '物理', '化学', '生物', '未知',
].map(v => ({ label: v, value: v }))

export const TYPE_OPTIONS = [
  '选择题', '填空题', '计算题', '证明题', '应用题', '未知',
].map(v => ({ label: v, value: v }))

export const GRADE_OPTIONS = [
  '初中', '高中', '通用',
].map(v => ({ label: v, value: v }))

export const DIFFICULTY_OPTIONS = [
  '简单', '中等', '困难',
].map(v => ({ label: v, value: v }))