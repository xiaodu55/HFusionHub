package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 废标风险自检报告实体（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_check_report")
@Schema(description = "废标风险自检报告实体")
public class BidCheckReport extends BaseEntity {

    /** 严重度 */
    public static final String SEVERITY_CRITICAL = "critical";
    public static final String SEVERITY_WARNING = "warning";
    public static final String SEVERITY_INFO = "info";

    /** 检查类别 */
    public static final String CATEGORY_DISQUALIFICATION = "disqualification";
    public static final String CATEGORY_SUBSTANTIVE = "substantive";
    public static final String CATEGORY_FORMAT = "format";
    public static final String CATEGORY_BOND = "bond";
    public static final String CATEGORY_DEADLINE = "deadline";

    /** 处理状态 */
    public static final String STATUS_OPEN = "open";
    public static final String STATUS_CONFIRMED = "confirmed";
    public static final String STATUS_FIXED = "fixed";

    @TableId(type = IdType.AUTO)
    @Schema(description = "报告ID")
    private Long id;

    @Schema(description = "投标项目ID")
    private Long projectId;

    @Schema(description = "定位分节（可空=项目级）")
    private String sectionKey;

    @Schema(description = "严重度：critical|warning|info")
    private String severity;

    @Schema(description = "检查类别：disqualification|substantive|format|bond|deadline")
    private String category;

    @Schema(description = "问题描述")
    private String finding;

    @Schema(description = "证据引用 JSON")
    private String evidence;

    @Schema(description = "修复建议")
    private String suggestedFix;

    @Schema(description = "处理状态：open|confirmed|fixed")
    private String status;
}
