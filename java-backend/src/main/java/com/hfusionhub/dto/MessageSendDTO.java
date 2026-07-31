package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import jakarta.validation.constraints.Size;
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
    @Size(max = 4000, message = "消息内容不能超过4000个字符")
    private String content;

    @Schema(description = "客户端请求幂等ID，用于SSE重连去重")
    @Size(max = 80, message = "请求ID不能超过80个字符")
    private String requestId;

    @Schema(
            description = "能力档位（Agent V1 Step 5）。null/absent = V1.0只读；"
                    + "\"approval_write\" = V1.1受控写（write_note可见→approval_required门控）。"
                    + "服务端必须按业务权限策略决定是否允许，不能直接信任客户端。"
                    + "普通聊天始终强制null。")
    @Size(max = 50, message = "能力档位标识不能超过50个字符")
    private String capabilityProfile;

    @Schema(description = "附带图片的相对URL列表（对话图片输入，≤4张；"
            + "先经 POST /conversation/chat-image 上传取得 URL）")
    @Size(max = 4, message = "每次最多携带4张图片")
    private List<String> images;
}
