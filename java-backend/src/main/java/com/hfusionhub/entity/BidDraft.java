package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 标书分节草稿实体（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_draft")
@Schema(description = "标书分节草稿实体")
public class BidDraft extends BaseEntity {

    /** 分节键：商务/技术/资质/格式 */
    public static final String SECTION_COMMERCIAL = "commercial";
    public static final String SECTION_TECHNICAL = "technical";
    public static final String SECTION_QUALIFICATION = "qualification";
    public static final String SECTION_FORMAT = "format";

    /** 分节状态 */
    public static final String STATUS_DRAFTING = "drafting";
    public static final String STATUS_APPROVED = "approved";
    public static final String STATUS_REJECTED = "rejected";

    @TableId(type = IdType.AUTO)
    @Schema(description = "草稿ID")
    private Long id;

    @Schema(description = "投标项目ID")
    private Long projectId;

    @Schema(description = "分节键：commercial|technical|qualification|format")
    private String sectionKey;

    @Schema(description = "分节标题")
    private String sectionTitle;

    @Schema(description = "分节正文（长文）")
    private String content;

    @Schema(description = "分节状态：drafting|approved|rejected")
    private String status;

    @Schema(description = "分节版本号")
    private Integer version;

    @Schema(description = "审批人ID")
    private Long approvedBy;

    @Schema(description = "创建人ID")
    private Long createdBy;
}
