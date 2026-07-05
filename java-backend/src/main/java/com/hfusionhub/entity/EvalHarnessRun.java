package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.hfusionhub.handler.JsonMapTypeHandler;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.Map;

/**
 * 评估中枢运行记录（V79）：python eval_harness 评估的聚合摘要。
 * 逐样本明细保留在 python 侧 JSONL/报告中，本表只存聚合指标与失败用例标识。
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("eval_harness_runs")
public class EvalHarnessRun extends BaseEntity {

    /** 运行ID */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** python 侧运行文件名（&lt;label&gt;_&lt;ts&gt;.jsonl） */
    private String runFile;

    private String label;

    private Long knowledgeBaseId;

    private Integer topK;

    private Integer recordCount;

    private Integer requiresRagCount;

    /** 是否启用 LLM 评审 */
    private Integer judgeEnabled;

    /** LLM 评审条数 */
    private Integer judgeCases;

    /** 聚合指标（检索/行为/TTFT/judge） */
    @TableField(typeHandler = JsonMapTypeHandler.class)
    private Map<String, Object> overall;

    /** 未命中用例 ID 列表 */
    @TableField(typeHandler = JsonMapTypeHandler.class)
    private Map<String, Object> failedCaseIds;

    private Long tenantId;
}
