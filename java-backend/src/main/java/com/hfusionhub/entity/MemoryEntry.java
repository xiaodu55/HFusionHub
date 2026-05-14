package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import jakarta.validation.constraints.NotBlank;
import java.time.LocalDateTime;
import lombok.Data;

@Data
@TableName("memory_entry")
public class MemoryEntry {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    /** conversation_summary | entity_fact | user_preference */
    @NotBlank(message = "记忆类型不能为空")
    private String type;

    @NotBlank(message = "记忆内容不能为空")
    private String content;

    /** JSON array of entity names */
    private String entities;

    private Long conversationId;

    private Long knowledgeBaseId;

    /** 0.0-1.0 importance score */
    private Double importance;

    /** NULL means that the user keeps this memory indefinitely. */
    private LocalDateTime expiresAt;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
