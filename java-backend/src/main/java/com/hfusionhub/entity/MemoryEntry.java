package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;
import java.util.List;

@Data
@TableName("memory_entry")
public class MemoryEntry {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    /** conversation_summary | entity_fact | user_preference */
    private String type;

    private String content;

    /** JSON array of entity names */
    private String entities;

    private Long conversationId;

    private Long knowledgeBaseId;

    /** 0.0-1.0 importance score */
    private Double importance;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
