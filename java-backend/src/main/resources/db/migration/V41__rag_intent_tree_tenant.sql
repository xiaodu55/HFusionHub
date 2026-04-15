ALTER TABLE rag_intent_node
    ADD COLUMN tenant_id BIGINT NOT NULL DEFAULT 1 COMMENT 'Tenant ID' AFTER user_id,
    ADD KEY idx_rag_intent_tenant_parent (tenant_id, parent_id, deleted, sort_order);
