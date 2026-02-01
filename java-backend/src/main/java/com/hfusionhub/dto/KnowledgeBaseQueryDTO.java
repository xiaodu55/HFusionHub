package com.hfusionhub.dto;

import com.hfusionhub.common.dto.PageQuery;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 知识库查询请求
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Schema(description = "知识库查询请求")
public class KnowledgeBaseQueryDTO extends PageQuery {

    @Schema(description = "知识库名称（模糊查询）", example = "测试")
    private String name;

    @Schema(description = "状态：0-正常，1-禁用")
    private Integer status;
}
