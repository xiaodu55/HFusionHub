package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 文档更新请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "文档更新请求")
public class DocumentUpdateDTO {

    @Size(min = 1, max = 200, message = "文档标题长度必须在1-200之间")
    @Schema(description = "文档标题", example = "更新后的文档标题")
    private String title;

    @Schema(description = "文档内容", example = "更新后的文档内容")
    private String content;

    @Schema(description = "可见性等级：general/confidential（缺省不修改）", example = "general")
    private String visibility;
}
