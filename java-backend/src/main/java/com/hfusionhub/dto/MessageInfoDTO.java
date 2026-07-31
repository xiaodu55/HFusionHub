package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Data;

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
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;

    @Schema(description = "知识来源")
    private List<Map<String, Object>> sources;

    @Schema(description = "Agent V1 状态：completed | insufficient_evidence | tool_error | timeout")
    private String status;

    @Schema(description = "Agent V1 运行标识")
    private String agentRunId;

    @Schema(description = "Agent V1 工具调用次数")
    private Integer toolCallsCount;
    /** 用户消息附带图片的相对 URL 列表（对话图片输入）；null = 无图片 */
    private java.util.List<String> images;
}
