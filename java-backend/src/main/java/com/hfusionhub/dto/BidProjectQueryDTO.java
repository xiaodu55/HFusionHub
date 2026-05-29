package com.hfusionhub.dto;

import com.hfusionhub.common.dto.PageQuery;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 投标项目查询请求（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Schema(description = "投标项目查询请求")
public class BidProjectQueryDTO extends PageQuery {

    @Schema(description = "项目名称/招标编号（模糊查询）", example = "园区")
    private String keyword;

    @Schema(description = "状态：interpreting|requirements|drafting|checking|submitted|archived")
    private String status;
}
