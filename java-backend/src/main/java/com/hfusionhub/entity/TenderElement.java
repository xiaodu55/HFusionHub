package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 招标文件结构化要素实体（招投标垂直化）
 *
 * <p>由 Python 解读工作流产出、Java 落库；(project_id, element_key) 唯一。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("tender_element")
@Schema(description = "招标文件结构化要素实体")
public class TenderElement extends BaseEntity {

    /** 要素键枚举 */
    public static final String KEY_TENDER_NUMBER = "tender_number";
    public static final String KEY_BUDGET = "budget";
    public static final String KEY_QUALIFICATION_REQUIREMENTS = "qualification_requirements";
    public static final String KEY_SCORING_METHOD = "scoring_method";
    public static final String KEY_DEADLINE = "deadline";
    public static final String KEY_BID_BOND = "bid_bond";
    public static final String KEY_DISQUALIFICATION_CLAUSES = "disqualification_clauses";
    public static final String KEY_SUBSTANTIVE_RESPONSE_CLAUSES = "substantive_response_clauses";
    public static final String KEY_BID_CURRENCY = "bid_currency";
    public static final String KEY_CONTACT = "contact";

    @TableId(type = IdType.AUTO)
    @Schema(description = "要素ID")
    private Long id;

    @Schema(description = "投标项目ID")
    private Long projectId;

    @Schema(description = "要素键")
    private String elementKey;

    @Schema(description = "要素内容（JSON 或文本）")
    private String elementValue;

    @Schema(description = "证据 chunk id 列表（JSON 数组）")
    private String evidenceChunkIds;

    @Schema(description = "置信度 0-1")
    private BigDecimal confidence;

    @Schema(description = "来源条款原文")
    private String sourceClause;
}
