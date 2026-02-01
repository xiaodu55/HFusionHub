package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 文档上传请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "文档上传请求")
public class DocumentUploadDTO {

    @NotNull(message = "知识库ID不能为空")
    @Schema(description = "知识库ID", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long knowledgeBaseId;

    @NotBlank(message = "文档标题不能为空")
    @Schema(description = "文档标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "测试文档")
    private String title;
}
