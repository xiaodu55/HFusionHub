-- V75: 移除 tender_element 的 (project_id, element_key) 唯一键
--
-- 背景: 解读工作流的废标/实质性条款专家会为同类别输出多条要素
-- (如每条废标条款各一行 element_key='disqualification_clauses'),
-- 唯一键导致真实招标文件解读落库时抛
-- Duplicate entry '...-disqualification_clauses' 而整体 500.
-- 幂等由 interpret() 的"先删后写"保证, 唯一键并无必要.
ALTER TABLE tender_element DROP INDEX uk_tender_element;
