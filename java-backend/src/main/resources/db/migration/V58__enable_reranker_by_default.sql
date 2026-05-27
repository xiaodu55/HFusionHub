-- V58: 上线第二级重排（Reranker）。
-- 二级重排阶段（lexical 零依赖安全默认 / cross_encoder 可选模型升级）已完成验证，
-- 将 rag.reranker.enabled 默认置为 TRUE，使重排阶段在检索管线上默认生效。
-- 仍可在前端「能力开关」页按需关闭。
UPDATE feature_flag SET enabled = TRUE WHERE flag_key = 'rag.reranker.enabled';
