package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Durable record of one document indexing attempt.
 *
 * <p>The Python worker is deliberately treated as stateless.  This table is
 * the source of truth for retrying, rejecting stale callbacks, and diagnosing
 * a document that was interrupted while it was being embedded.</p>
 */
@Data
@TableName("document_index_job")
public class DocumentIndexJob extends BaseEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long documentId;
    private Long knowledgeBaseId;
    private String indexVersion;
    private String embeddingModel;
    private Integer embeddingDimension;
    private String embeddingVersion;
    private String status;
    private Integer attempt;
    private Integer chunkCount;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime completedAt;
}
