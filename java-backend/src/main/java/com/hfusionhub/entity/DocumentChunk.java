package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/**
 * Persisted, non-vector metadata for a retrievable document chunk.
 *
 * <p>Chunk text remains in the vector store; the database keeps the stable
 * citation fields needed after a Python worker restart.</p>
 */
@Data
@TableName("document_chunk")
public class DocumentChunk {

    @TableId
    private String chunkId;

    private Long documentId;
    private Long knowledgeBaseId;
    private String indexVersion;
    private Integer chunkIndex;
    private String blockType;
    private String outlinePath;
    private String contentExcerpt;
    private Integer charCount;
    private String metadata;
    private String embeddingModel;
    private Integer embeddingDimension;
    private String embeddingVersion;
}
