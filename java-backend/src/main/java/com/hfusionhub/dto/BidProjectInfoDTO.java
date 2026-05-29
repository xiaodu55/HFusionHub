package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 投标项目信息返回（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "投标项目信息返回")
public class BidProjectInfoDTO {

    @Schema(description = "投标项目ID")
    private Long id;

    @Schema(description = "招标文件知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "招标编号")
    private String tenderNumber;

    @Schema(description = "项目名称")
    private String title;

    @Schema(description = "预算金额（元）")
    private BigDecimal budget;

    @Schema(description = "工期/交货期")
    private String deadline;

    @Schema(description = "投标保证金要求")
    private String bidBond;

    @Schema(description = "开标时间")
    private LocalDateTime openingDate;

    @Schema(description = "状态")
    private String status;

    @Schema(description = "创建人ID")
    private Long createdBy;

    @Schema(description = "需求数量")
    private Integer requirementCount;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
