package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;
import lombok.Data;

/**
 * 开放 API 对话请求（/openapi/chat）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "开放 API 对话请求")
public class OpenApiChatRequest {

    @Schema(description = "用户问题")
    private String query;

    @Schema(description = "历史对话（OpenAI 格式）")
    private List<Map<String, String>> history;
}
