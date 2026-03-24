package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 对话创建请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "对话创建请求")
public class ConversationCreateDTO {

    @Schema(description = "关联知识库ID", example = "1")
    private Long knowledgeBaseId;

    @Schema(description = "已发布的提示词模板 ID（可选）", example = "1")
    private Long promptTemplateId;

    @Size(max = 200, message = "标题长度不能超过200")
    @Schema(description = "对话标题", example = "测试对话")
    private String title;
}
