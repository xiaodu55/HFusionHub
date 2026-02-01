package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 知识库更新请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "知识库更新请求")
public class KnowledgeBaseUpdateDTO {

    @Size(min = 1, max = 100, message = "知识库名称长度必须在1-100之间")
    @Schema(description = "知识库名称", example = "新知识库名称")
    private String name;

    @Size(max = 500, message = "描述长度不能超过500")
    @Schema(description = "知识库描述", example = "更新后的描述")
    private String description;

    @Schema(description = "状态：0-正常，1-禁用")
    private Integer status;
}
