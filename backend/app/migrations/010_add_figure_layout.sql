-- 010: 题图排版（老师自定义）
--
-- 为什么加这两个字段
-- ----------------
-- 老师反馈「按排版美化来说，题图放到题目右下方比较合适」。
-- 排版是**每道题自己的诉求**：有的题图大、有的题图小，
-- 有的老师习惯图在右下（教材式），有的习惯图在下方居中。
-- 所以版式存到题上，而不是写死在导出模板里。
--
-- figure_layout 取值：
--   bottom_right  题图在右下角（默认，文字在左、图在右下）
--   right        题图在右侧，与文字顶部对齐
--   bottom_left  题图在下方靠左（旧版排版）
--   bottom_center 题图在下方居中
--   none         不显示题图
--
-- figure_width = 题图宽度占题目宽度的百分比，0 = 用该版式的默认宽度。
ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS figure_layout VARCHAR(20) NOT NULL DEFAULT 'bottom_right';

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS figure_width INTEGER NOT NULL DEFAULT 0;
