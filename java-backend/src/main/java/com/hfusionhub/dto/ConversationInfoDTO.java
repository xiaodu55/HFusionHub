package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对话信息返回
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "对话信息返回")
public class ConversationInfoDTO {

    @Schema(description = "对话ID")
    private Long id;

    @Schema(description = "关联知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "创建人名称")
    private String userName;

    @Schema(description = "对话标题")
    private String title;

    @Schema(description = "消息数量")
    private Integer messageCount;

    @Schema(description = "最后一条消息内容")
    private String lastMessage;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
