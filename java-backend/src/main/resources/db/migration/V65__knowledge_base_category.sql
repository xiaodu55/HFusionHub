-- V65: 招投标垂直化 —— 知识库分类
-- 区分三类私有库：tender(招标文件库)/qualification(企业资质库)/bid_history(历史标书库) + 通用 general
ALTER TABLE knowledge_base
    ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'general' COMMENT 'general|tender|qualification|bid_history';
