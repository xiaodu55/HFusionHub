package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 投标需求清单实体（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_requirement")
@Schema(description = "投标需求清单实体")
public class BidRequirement extends BaseEntity {

    /** 需求类别 */
    public static final String CATEGORY_QUALIFICATION = "qualification";
    public static final String CATEGORY_PERFORMANCE = "performance";
    public static final String CATEGORY_TECHNICAL = "technical";
    public static final String CATEGORY_COMMERCIAL = "commercial";
    public static final String CATEGORY_FORMAT = "format";
    public static final String CATEGORY_DISQUALIFICATION_RISK = "disqualification_risk";

    /** 满足状态 */
    public static final String STATUS_PENDING = "pending";
    public static final String STATUS_DRAFTING = "drafting";
    public static final String STATUS_CHECKED = "checked";
    /** 低置信要素强制人工确认 */
    public static final String STATUS_MANUAL_REVIEW = "manual_review";

    @TableId(type = IdType.AUTO)
    @Schema(description = "需求ID")
    private Long id;

    @Schema(description = "投标项目ID")
    private Long projectId;

    @Schema(description = "需求类别：qualification|performance|technical|commercial|format|disqualification_risk")
    private String category;

    @Schema(description = "需求描述")
    private String requirement;

    @Schema(description = "来源条款原文")
    private String sourceClause;

    @Schema(description = "满足状态：pending|drafting|checked|manual_review")
    private String satisfiedStatus;
}
