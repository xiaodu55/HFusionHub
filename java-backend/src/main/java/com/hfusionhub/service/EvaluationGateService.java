package com.hfusionhub.service;

import com.hfusionhub.dto.GateResult;
import com.hfusionhub.entity.EvaluationGateResult;

import java.util.List;

/**
 * 评测回归门禁服务
 *
 * @author HFusionHub Team
 */
public interface EvaluationGateService {

    /**
     * 对指定评测执行记录执行回归门禁检查（当前登录用户视角）。
     *
     * @param datasetId 评测集ID
     * @param runId     评测执行记录ID
     * @return 门禁结果
     */
    GateResult checkGate(Long datasetId, Long runId);

    /**
     * 对指定评测执行记录执行回归门禁检查。
     *
     * <p>门禁规则：accuracy &gt; 0.8，latency_p95 &lt; 5000ms，
     * token_cost &lt; 基线成本 × 1.2（基线为同数据集最近一次 completed 的评测）。
     * 结果会持久化并触发 {@code evaluation.completed} Webhook 事件。</p>
     *
     * @param userId    用户ID（用于数据集归属校验）
     * @param datasetId 评测集ID
     * @param runId     评测执行记录ID
     * @return 门禁结果
     */
    GateResult checkGate(Long userId, Long datasetId, Long runId);

    /**
     * 评测集的门禁通过/失败历史（分页，仅本人）
     *
     * @param userId    用户ID
     * @param datasetId 评测集ID
     * @param page      页码（从 1 开始）
     * @param pageSize  每页条数（1-100）
     * @return 门禁结果列表（按检查时间倒序）
     */
    List<EvaluationGateResult> gateHistory(Long userId, Long datasetId, int page, int pageSize);
}
