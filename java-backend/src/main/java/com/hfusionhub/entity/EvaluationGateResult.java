package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 评测回归门禁结果实体
 *
 * <p>每次执行评测门禁（checkGate）持久化一条记录，供门禁通过/失败历史查询。
 * 表无 tenant_id / deleted 列（访问受数据集归属校验保护，与
 * {@code agent_evaluation_run} 同模式），已登记在租户行拦截器的忽略表中。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("evaluation_gate_result")
@Schema(description = "评测回归门禁结果")
public class EvaluationGateResult {

    @TableId(type = IdType.AUTO)
    @Schema(description = "记录ID")
    private Long id;

    @Schema(description = "评测集ID")
    private Long datasetId;

    @Schema(description = "评测执行记录ID")
    private Long runId;

    @Schema(description = "评测执行UUID")
    private String runUuid;

    @Schema(description = "是否通过门禁：1-通过，0-未通过")
    private Integer passed;

    @Schema(description = "综合准确率（0-1）")
    private BigDecimal accuracy;

    @Schema(description = "P95 延迟（毫秒）")
    private Integer latencyP95;

    @Schema(description = "本次 token 成本（美元）")
    private BigDecimal tokenCost;

    @Schema(description = "基线评测 UUID")
    private String baselineRunUuid;

    @Schema(description = "基线 token 成本（美元）")
    private BigDecimal baselineTokenCost;

    @Schema(description = "门禁判定明细（JSON 数组字符串）")
    private String criteriaJson;

    @Schema(description = "补充说明（JSON 字符串）")
    private String details;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "门禁检查时间")
    private LocalDateTime createdAt;
}
