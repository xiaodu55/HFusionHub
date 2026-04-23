package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/** Immutable snapshot of a prompt template at a specific version. */
@Data
@TableName("prompt_template_version")
public class PromptTemplateVersion {

    /** Operation types recorded in the audit trail. */
    public static final String OP_CREATE = "CREATE";

    public static final String OP_EDIT = "EDIT";
    public static final String OP_PUBLISH = "PUBLISH";
    public static final String OP_UNPUBLISH = "UNPUBLISH";
    public static final String OP_ROLLBACK = "ROLLBACK";

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long templateId;
    private Integer version;
    private String name;
    private String description;
    private String content;
    private String status;
    private String operation;
    private Long operatorId;
    private java.time.LocalDateTime createdAt;
}
