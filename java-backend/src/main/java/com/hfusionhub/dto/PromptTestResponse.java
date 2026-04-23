package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Data;

/**
 * 提示词测试台响应
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "提示词测试台响应")
public class PromptTestResponse {

    @Schema(description = "AI 回答内容（Markdown）", example = "RAG（Retrieval-Augmented Generation）是一种...")
    private String content;

    @Schema(description = "使用的模型名称", example = "deepseek-v3")
    private String model;

    @Schema(description = "总 token 消耗", example = "1234")
    private int tokenCount;

    @Schema(
            description = "详细 token 用量",
            example = "{\"prompt_tokens\":500,\"completion_tokens\":734,\"total_tokens\":1234}")
    private Map<String, Object> tokenUsage;

    @Schema(description = "引用来源列表")
    private List<Map<String, Object>> sources;

    @Schema(description = "服务端耗时（毫秒）", example = "1234")
    private long elapsedMs;
}
