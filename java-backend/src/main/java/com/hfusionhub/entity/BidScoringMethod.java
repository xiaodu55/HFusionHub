package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 招标评分办法实体（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_scoring_method")
@Schema(description = "招标评分办法实体")
public class BidScoringMethod extends BaseEntity {

    /** 综合评分法 */
    public static final String TYPE_COMPREHENSIVE = "comprehensive";
    /** 最低价法 */
    public static final String TYPE_LOWEST_PRICE = "lowest_price";

    @TableId(type = IdType.AUTO)
    @Schema(description = "评分办法ID")
    private Long id;

    @Schema(description = "投标项目ID")
    private Long projectId;

    @Schema(description = "评分方式：comprehensive|lowest_price")
    private String methodType;

    @Schema(description = "评分点 JSON：[{name,max_score,weight,scoring_criteria,evidence}]")
    private String pointsJson;

    @Schema(description = "满分")
    private BigDecimal totalScore;
}
