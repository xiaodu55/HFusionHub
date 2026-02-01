package com.hfusionhub.dto;

import com.hfusionhub.common.dto.PageQuery;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 对话查询请求
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Schema(description = "对话查询请求")
public class ConversationQueryDTO extends PageQuery {

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "对话标题（模糊查询）")
    private String title;
}
