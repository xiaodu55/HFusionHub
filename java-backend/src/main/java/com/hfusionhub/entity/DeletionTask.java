package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import java.io.Serializable;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 删除任务实体 — 知识库/文档异步删除的 Outbox
 *
 * @author HFusionHub Team
 */
@Data
@TableName("deletion_task")
public class DeletionTask implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(type = IdType.AUTO)
    private Long id;

    /** KB_DELETE / DOCUMENT_DELETE */
    private String taskType;

    /** 知识库ID 或 文档ID */
    private Long targetId;

    /** PENDING / PROCESSING / RETRYING / COMPLETED / FAILED */
    private String status;

    /** 当前执行步骤名称 */
    private String step;

    /** 当前步骤索引 (0-based) */
    private Integer stepIndex;

    private Integer maxRetries;

    private Integer retryCount;

    private String errorMessage;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
