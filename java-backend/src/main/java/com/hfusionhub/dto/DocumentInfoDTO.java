package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

/**
 * 文档信息返回
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "文档信息返回")
public class DocumentInfoDTO {

    @Schema(description = "文档ID")
    private Long id;

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "文档标题")
    private String title;

    @Schema(description = "文件类型")
    private String fileType;

    @Schema(description = "文件大小（字节）")
    private Long fileSize;

    @Schema(description = "分块数量")
    private Integer chunkCount;

    @Schema(description = "状态：0-处理中，1-成功，2-失败")
    private Integer status;

    @Schema(description = "状态描述")
    private String statusDesc;

    @Schema(description = "错误信息")
    private String errorMessage;

    @Schema(description = "上传者用户名")
    private String username;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;

    private LocalDateTime recycledAt;

    private LocalDateTime recycleExpiresAt;
}
