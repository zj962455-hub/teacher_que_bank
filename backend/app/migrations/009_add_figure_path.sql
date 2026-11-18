-- 009: 题目配图（几何示意图）
--
-- 为什么加这个字段
-- ----------------
-- OCR 只能读文字，认不出三角形、垂足、辅助线。
-- 灰度实测的典型样本：文字全对，图没了。
--
-- 于是「题目的原图」和「题目的配图」必须分开存：
--   image_path  = OCR 来源的那张截图（原图）
--   figure_path = 从原图里裁出来的几何示意图（导出试卷时带的是这张）
--
-- 老数据没有配图 —— 留空即可，不影响任何既有行为。
ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS figure_path VARCHAR(500) NOT NULL DEFAULT '';
