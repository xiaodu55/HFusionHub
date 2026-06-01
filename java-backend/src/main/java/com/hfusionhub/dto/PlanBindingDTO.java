package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 租户套餐绑定视图（绑定 + 套餐信息合并，招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "租户套餐绑定视图")
public class PlanBindingDTO {

    @Schema(description = "绑定ID")
    private Long bindingId;

    @Schema(description = "套餐ID")
    private Long subscriptionId;

    @Schema(description = "套餐代码 free|pro|enterprise|industry_*")
    private String planCode;

    @Schema(description = "套餐名称")
    private String planName;

    @Schema(description = "套餐类型：tier|industry")
    private String planType;

    @Schema(description = "月度价格（分）")
    private Long priceCents;

    @Schema(description = "最大投标项目数")
    private Integer maxProjects;

    @Schema(description = "最大坐席数")
    private Integer maxSeats;

    @Schema(description = "标书撰写月度字符额度")
    private Long charQuota;

    @Schema(description = "模块开关 JSON")
    private String moduleFlags;

    @Schema(description = "绑定状态：active|expired|canceled")
    private String status;

    @Schema(description = "生效时间")
    private LocalDateTime startAt;

    @Schema(description = "到期时间；NULL=长期")
    private LocalDateTime endAt;
}
