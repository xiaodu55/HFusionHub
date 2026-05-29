package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 标书模板实体（招投标垂直化 · P1）
 *
 * <p>{@code tenantId} 为空表示平台级模板（P2 行业方案包的基础）。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_template")
@Schema(description = "标书模板实体")
public class BidTemplate extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "模板ID")
    private Long id;

    @Schema(description = "租户ID；NULL=平台级模板")
    private Long tenantId;

    @Schema(description = "模板名称")
    private String name;

    @Schema(description = "模板说明")
    private String description;

    @Schema(description = "行业分类（工程施工/IT集成等）")
    private String industry;

    @Schema(description = "分节定义 JSON 数组")
    private String sectionDefs;

    @Schema(description = "是否启用")
    private Integer isActive;

    @Schema(description = "创建人ID")
    private Long createdBy;
}
