package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 知识库信息返回
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "知识库信息返回")
public class KnowledgeBaseInfoDTO {

    @Schema(description = "知识库ID")
    private Long id;

    @Schema(description = "知识库名称")
    private String name;

    @Schema(description = "知识库描述")
    private String description;

    @Schema(description = "创建者ID")
    private Long userId;

    @Schema(description = "创建者用户名")
    private String username;

    @Schema(description = "状态")
    private Integer status;

    @Schema(description = "移入回收站时间")
    private LocalDateTime recycledAt;

    @Schema(description = "回收站保留截止时间")
    private LocalDateTime recycleExpiresAt;

    @Schema(description = "文档数量")
    private Integer documentCount;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
