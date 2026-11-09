-- lesson-37: 题图排版收敛为三个选项（2026-11-09 老大定）
--   bottom_right = 题目文字下方·右下角（默认）
--   bottom_left  = 题目文字下方·左下角
--   none         = 不显示题图
-- 旧值 right / bottom_center 不再是可选版式，统一回落到默认（老师可在编辑器里改）。
UPDATE questions
   SET figure_layout = 'bottom_right'
 WHERE figure_layout IS NOT NULL
   AND figure_layout NOT IN ('bottom_right', 'bottom_left', 'none');
