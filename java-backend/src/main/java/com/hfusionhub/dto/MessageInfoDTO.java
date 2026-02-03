package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 消息信息返回
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "消息信息返回")
public class MessageInfoDTO {

    @Schema(description = "消息ID")
    private Long id;

    @Schema(description = "对话ID")
    private Long conversationId;

    @Schema(description = "角色：user-用户，assistant-助手，system-系统")
    private String role;

    @Schema(description = "消息内容")
    private String content;

    @Schema(description = "Token数量")
    private Integer tokenCount;

    @Schema(description = "使用的模型")
    private String model;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "知识来源")
    private List<Map<String, Object>> sources;
}
