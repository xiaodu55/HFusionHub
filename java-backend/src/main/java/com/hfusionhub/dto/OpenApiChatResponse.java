package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;
import lombok.Data;

/**
 * 开放 API 对话响应（/openapi/chat）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "开放 API 对话响应")
public class OpenApiChatResponse {

    @Schema(description = "回答内容")
    private String content;

    @Schema(description = "来源引用")
    private List<Map<String, Object>> sources;

    @Schema(description = "模型")
    private String model;

    @Schema(description = "状态：completed | insufficient_evidence | tool_error | timeout | waiting_approval")
    private String status;

    @Schema(description = "Token 用量")
    private Map<String, Object> tokenUsage;
}
