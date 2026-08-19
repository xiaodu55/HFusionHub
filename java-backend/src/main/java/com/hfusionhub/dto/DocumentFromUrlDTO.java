package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 从公开网页 URL 创建文档的请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "网页文档创建请求")
public class DocumentFromUrlDTO {

    @NotBlank(message = "网页地址不能为空")
    @Size(max = 2048, message = "网页地址过长")
    @Schema(description = "公开 HTTPS 网页地址", example = "https://example.com/doc")
    private String url;

    @Size(max = 200, message = "文档标题长度必须在200以内")
    @Schema(description = "可选标题（留空则取自网页 title）", example = "产品文档")
    private String title;

    @Schema(description = "可见性等级：general/confidential，缺省 general", example = "general")
    private String visibility;
}
