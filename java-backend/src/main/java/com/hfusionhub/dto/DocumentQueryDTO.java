package com.hfusionhub.dto;

import com.hfusionhub.common.dto.PageQuery;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 文档查询请求
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Schema(description = "文档查询请求")
public class DocumentQueryDTO extends PageQuery {

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "文档标题（模糊查询）")
    private String title;

    @Schema(description = "文档状态：0-处理中，1-成功，2-失败")
    private Integer status;
}
