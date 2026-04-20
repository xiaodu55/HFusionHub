package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 知识库共享实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("kb_share")
@Schema(description = "知识库共享")
public class KbShare extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "共享记录ID")
    private Long id;

    @Schema(description = "FK → knowledge_base.id")
    private Long knowledgeBaseId;

    @Schema(description = "知识库所有者")
    private Long ownerUserId;

    @Schema(description = "被共享用户")
    private Long sharedUserId;

    @Schema(description = "read | read_write（当前仅 read 生效）")
    private String permission;
}
