package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 消息发送请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "消息发送请求")
public class MessageSendDTO {

    @NotNull(message = "对话ID不能为空")
    @Schema(description = "对话ID", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long conversationId;

    @NotBlank(message = "消息内容不能为空")
    @Schema(description = "消息内容", requiredMode = Schema.RequiredMode.REQUIRED, example = "你好，请帮我分析一下这个文档")
    private String content;

    @Schema(description = "客户端请求幂等ID，用于SSE重连去重")
    private String requestId;
}
