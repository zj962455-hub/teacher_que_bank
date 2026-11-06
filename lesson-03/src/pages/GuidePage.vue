<script setup>
/**
 * GuidePage — 老师使用指南 — lesson-34
 *
 * 写给谁看
 * --------
 * **第一次用的老师** —— 不是管理员，不是开发者，就是「拿到账号要开始录题」的老师。
 * 所以写法是口语 + 一步一步，不讲技术名词。
 *
 * 为什么要有这个页面
 * ------------------
 * 灰度试用阶段，管理员（老大）不在老师旁边 —— 老师卡住了只能自己看页面。
 * 顶栏「反馈」是「出问题后」的出口，而这份指南是「出问题前」的预防：
 * 照着做一遍，基本不会卡。
 *
 * 纯前端页面：不需要后端接口。
 */
import { NCard, NAlert, NText, NSteps, NStep, NSpace, NTag } from 'naive-ui'

// === 七步 ===
const STEPS = [
  { title: '登录', desc: '用管理员给的账号密码进系统' },
  { title: '录题', desc: '拍照上传 → OCR 识别 → 校对 → 存库' },
  { title: '题库', desc: '分类、搜索、编辑、删除' },
  { title: '组卷', desc: '三栏组卷、拖拽排序、导出' },
  { title: '分享', desc: '生成带有效期的链接' },
  { title: '反馈', desc: '随手提意见，看处理状态' },
]
</script>

<template>
  <div class="guide">
    <NCard title="📖 使用指南" :bordered="false">
      <NAlert type="info" :bordered="false" style="margin-bottom: 16px">
        第一次用？按下面六步走一遍，十分钟就能上手。
        卡住了先用顶栏的「💬 反馈」说一声，会有人来改。
      </NAlert>

      <NSteps :current="6" size="small" style="margin-bottom: 20px">
        <NStep
          v-for="s in STEPS"
          :key="s.title"
          :title="s.title"
          :description="s.desc"
        />
      </NSteps>

      <!-- === 1. 登录 === -->
      <NCard size="small" :bordered="true" title="第一步 · 登录" style="margin-bottom: 12px">
        <ol class="steps">
          <li>打开管理员发给你的网址（就是本系统的地址）。</li>
          <li>
            在「用户名」里填管理员给你的账号，在「密码」里填初始密码，点「登录」。
          </li>
          <li>进去以后看到顶栏有「首页 / 题库 / 录题 / 分类 / 组卷」这些按钮，就说明登录成功了。</li>
        </ol>
        <NAlert type="warning" :bordered="false" style="margin-top: 10px">
          <b>共用账号：不要改密码。</b>
          现在大家用的是同一个账号，谁改了密码，其他人都会被踢下线（要重新登录）。
          个人中心里「修改密码」是灰的、点了也改不了 —— 这是故意的，不是坏了。
          真要改，找管理员。
        </NAlert>
      </NCard>

      <!-- === 2. 录题 === -->
      <NCard size="small" :bordered="true" title="第二步 · 录题（拍照 → 识别 → 校对 → 保存）" style="margin-bottom: 12px">
        <ol class="steps">
          <li>点顶栏「📷 录题」。</li>
          <li>
            <b>拍照或上传图片</b>：把试卷、练习册、卷子拍清楚（正着拍、光线均匀、别太歪），
            也可以从相册里选一张已有的照片。
          </li>
          <li>
            <b>点「🚀 开始识别」</b>：系统自动做 OCR，把图片里的文字和公式认出来。
            这一步大概要几秒钟，认完左边显示原图（红框标出认到的位置），右边显示识别结果。
          </li>
          <li>
            <b>校对（这一步最重要，别跳过）</b>：
            点「📝 转题目编辑器」，逐题检查。识别错的地方直接改。
          </li>
          <li>
            <b>点「💾 存入题库」</b>，题目就进你的题库了。
          </li>
        </ol>
        <NAlert type="error" :bordered="false" style="margin-top: 10px">
          <b>⚠️ OCR 会认错公式和文字，一定要校对。</b>
          图片模糊、公式复杂、上下标重叠的时候最容易认错 ——
          根号会变成方块，分式会少一半，负号可能就没了。
          直接拿去用，印出来的卷子会错。校对一遍只要几十秒，比印错一整张卷子划算。
        </NAlert>
      </NCard>

      <!-- === 3. 题库管理 === -->
      <NCard size="small" :bordered="true" title="第三步 · 题库管理" style="margin-bottom: 12px">
        <ol class="steps">
          <li>点顶栏「题库」，左边是筛选条件，右边是题目列表。</li>
          <li>
            <b>分类</b>：每道题可以归到「章节」里（比如「函数与导数」）。
            左侧勾章节就能只看这一章的题。
          </li>
          <li>
            <b>搜索</b>：在「搜题干关键词」里输入题目里出现的字，点「搜索」就能筛出来。
            还能按学科、题型、学段、难度一起过滤。
          </li>
          <li>
            <b>编辑</b>：点题目进详情页，改题干、改分类、改难度，改完记得保存。
          </li>
          <li>
            <b>删除</b>：在列表里勾选题目，点「删除」；也可以在详情页单题删除。
            勾选后还能「批量修改」分类、批量删除。
          </li>
        </ol>
        <NSpace style="margin-top: 8px">
          <NTag size="small" :bordered="false">📊 导出 Excel</NTag>
          <NText depth="3" style="font-size: 12px">
            题目多的时候可以导一份 Excel 备份，放心整理。
          </NText>
        </NSpace>
      </NCard>

      <!-- === 4. 组卷 === -->
      <NCard size="small" :bordered="true" title="第四步 · 组卷（三栏）" style="margin-bottom: 12px">
        <ol class="steps">
          <li>点顶栏「组卷」，先「+ 新建试卷」，给卷子起个名字（比如「高一数学第一单元测试」）。</li>
          <li>
            <b>左栏「📚 选题」</b>：按学科、难度、学段筛，或者直接搜题干，
            点题目右边的「+」加进卷子。
          </li>
          <li>
            <b>中栏「📝 试卷」</b>：已经加进来的题。
            拖动左边的「⠿」可以<b>调整顺序</b>；
            题号和分值都能改（题号可以写成「一、」「(1)」这种）。
          </li>
          <li>
            <b>右栏「👀 预览」</b>：看看排版对不对。
          </li>
          <li>
            <b>导出</b>：点「导出 PDF」出印刷版，点「导出 JPG」出图片版（发微信用）。
          </li>
        </ol>
      </NCard>

      <!-- === 5. 分享 === -->
      <NCard size="small" :bordered="true" title="第五步 · 分享给家长和学生" style="margin-bottom: 12px">
        <ol class="steps">
          <li>在「我的试卷」里打开一张卷子，进入导出页，往下滚到「🔗 分享链接」。</li>
          <li>选个有效期（几小时 / 几天 / 一周），点「生成分享链接」。</li>
          <li>点「复制链接」，发到微信群或家长群。</li>
        </ol>
        <NAlert type="info" :bordered="false" style="margin-top: 10px">
          对方<b>不用账号</b>，点开链接就能看卷子、下 PDF / JPG。
          链接<b>必带过期时间</b>（不会一直有效），也能随时吊销。
        </NAlert>
      </NCard>

      <!-- === 6. 反馈 === -->
      <NCard size="small" :bordered="true" title="第六步 · 提反馈" style="margin-bottom: 12px">
        <ol class="steps">
          <li>
            遇到不顺手的地方（按钮点不动、公式显示不对、想加个功能），
            点顶栏右上角的「💬 反馈」。
          </li>
          <li>
            选一下是「功能异常 / 功能建议 / 其它」，<b>写清楚哪里不对</b>
            （哪个页面、点了哪里、期望是什么样）。
          </li>
          <li>
            填一下「你是哪位老师」（默认是你的名字，改一下就行），
            联系方式可以填也可以不填 —— 填了管理员才好回你。
          </li>
          <li>点「提交反馈」。</li>
          <li>
            想看处理得怎么样了：顶栏「反馈记录」里能看到你提过的每一条，
            状态会从「待处理」变成「已读」、最后变成「已处理」。
          </li>
        </ol>
      </NCard>

      <!-- === 常见问题 === -->
      <NCard size="small" :bordered="true" title="常见问题">
        <div class="faq">
          <div class="faq-q">Q：识别出来的公式不对 / 变成方块了怎么办？</div>
          <div class="faq-a">
            A：OCR 认不准公式是常事，尤其是分式、根号、上下标。
            在「转题目编辑器」里直接改就行 —— 也可以拍得更清楚一点（正着拍、光线足、别太斜）再重新识别一次。
          </div>

          <div class="faq-q">Q：为什么我不能改密码？</div>
          <div class="faq-a">
            A：现在是大家共用一个账号，你一改密码其他人就都被踢下线了，
            所以系统把改密功能关掉了。要改密码找管理员单独处理。
          </div>

          <div class="faq-q">Q：分享链接打不开了？</div>
          <div class="faq-a">
            A：分享链接有有效期，过期了就打不开了。
            回「我的试卷」重新生成一个就行（记得重新选有效期）。
          </div>
        </div>
      </NCard>
    </NCard>
  </div>
</template>

<style scoped>
.guide {
  max-width: 860px;
  margin: 0 auto;
}

.steps {
  margin: 0;
  padding-left: 20px;
  line-height: 1.9;
  font-size: 14px;
}

.steps li {
  margin-bottom: 2px;
}

.faq-q {
  font-weight: 600;
  font-size: 14px;
  margin-top: 12px;
}

.faq-a {
  font-size: 13px;
  line-height: 1.8;
  color: var(--tqb-text-secondary);
  margin-top: 2px;
}
</style>
