-- 主体级 ACL：文档可见性等级（V85）
-- visibility 表示文档的敏感等级，向量分块随索引写入 Milvus chunk metadata，
-- 检索时按请求主体（X-User-Clearance）的 clearance 过滤：
--   general      - 一般文档，全部主体可见
--   confidential - 受控文档，仅 admin（全 clearance）主体可见
-- 既有数据缺省为 general，与 Python 侧"metadata 缺失按 general 处理"的
-- 后过滤语义一致（存量向量无需回填）。
ALTER TABLE document
    ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'general' COMMENT '文档可见性等级：general/confidential(V85)';
