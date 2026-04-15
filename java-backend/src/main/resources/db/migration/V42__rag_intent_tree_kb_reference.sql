ALTER TABLE rag_intent_node
    DROP FOREIGN KEY fk_rag_intent_kb,
    ADD CONSTRAINT fk_rag_intent_kb_setnull
        FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base(id)
        ON DELETE SET NULL
        ON UPDATE RESTRICT;
