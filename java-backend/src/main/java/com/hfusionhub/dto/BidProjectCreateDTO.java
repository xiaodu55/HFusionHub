package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 投标项目创建请求（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "投标项目创建请求")
public class BidProjectCreateDTO {

    @NotNull(message = "招标文件知识库不能为空")
    @Schema(description = "招标文件知识库ID（category=tender）", requiredMode = Schema.RequiredMode.REQUIRED)
    private Long knowledgeBaseId;

    @NotBlank(message = "项目名称不能为空")
    @Size(min = 1, max = 255, message = "项目名称长度必须在1-255之间")
    @Schema(description = "项目名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "某园区智能化改造项目")
    private String title;

    @Schema(description = "招标编号", example = "ZZCG2026-001")
    private String tenderNumber;

    @Schema(description = "预算金额（元）", example = "1200000.00")
    private BigDecimal budget;

    @Schema(description = "工期/交货期", example = "合同签订后60日历天")
    private String deadline;

    @Schema(description = "投标保证金要求", example = "投标保证金2万元，须于开标前1日到账")
    private String bidBond;

    @Schema(description = "开标时间")
    private LocalDateTime openingDate;
}
