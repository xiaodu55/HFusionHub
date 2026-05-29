package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 投标项目实体（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_project")
@Schema(description = "投标项目实体")
public class BidProject extends BaseEntity {

    /** 项目状态机 */
    public static final String STATUS_INTERPRETING = "interpreting";
    public static final String STATUS_REQUIREMENTS = "requirements";
    public static final String STATUS_DRAFTING = "drafting";
    public static final String STATUS_CHECKING = "checking";
    public static final String STATUS_SUBMITTED = "submitted";
    public static final String STATUS_ARCHIVED = "archived";

    @TableId(type = IdType.AUTO)
    @Schema(description = "投标项目ID")
    private Long id;

    /** 招标文件所在知识库 FK → knowledge_base.id（category=tender） */
    @Schema(description = "招标文件知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "招标编号")
    private String tenderNumber;

    @Schema(description = "项目名称")
    private String title;

    @Schema(description = "预算金额")
    private BigDecimal budget;

    @Schema(description = "工期/交货期")
    private String deadline;

    @Schema(description = "投标保证金要求")
    private String bidBond;

    @Schema(description = "开标时间")
    private LocalDateTime openingDate;

    @Schema(description = "状态：interpreting|requirements|drafting|checking|submitted|archived")
    private String status;

    @Schema(description = "创建人 sys_user.id")
    private Long createdBy;

    /** 非数据库字段：关联需求数量 */
    @TableField(exist = false)
    @Schema(description = "需求数量")
    private Integer requirementCount;
}
