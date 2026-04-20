package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 知识库共享信息
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "知识库共享信息")
public class KbShareInfoDTO {

    @Schema(description = "共享记录ID")
    private Long id;

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "知识库所有者ID")
    private Long ownerUserId;

    @Schema(description = "所有者用户名")
    private String ownerUsername;

    @Schema(description = "被共享用户ID")
    private Long sharedUserId;

    @Schema(description = "被共享用户名")
    private String sharedUsername;

    @Schema(description = "read | read_write")
    private String permission;

    @Schema(description = "共享时间")
    private LocalDateTime createdAt;
}
