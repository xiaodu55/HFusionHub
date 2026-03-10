package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.entity.AgentEvaluationCase;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.AgentEvaluationRun;

import java.util.List;
import java.util.Map;

/**
 * Agent 离线评测集管理与评测执行服务
 *
 * @author HFusionHub Team
 */
public interface AgentEvaluationService {

    // ── 评测集 CRUD ──

    AgentEvaluationDataset createDataset(AgentEvaluationDataset dataset);
    AgentEvaluationDataset getDataset(Long datasetId);
    List<AgentEvaluationDataset> listDatasets(Long userId, Long kbId, int page, int pageSize);
    void deleteDataset(Long datasetId);

    // ── 用例管理 ──

    AgentEvaluationCase addCase(AgentEvaluationCase evalCase);
    List<AgentEvaluationCase> getCases(Long datasetId);
    void deleteCase(Long caseId);

    // ── 评测执行 ──

    /**
     * 执行离线评测 — 将用例发送给 Python AI 服务进行评测。
     * 返回评测执行记录。
     */
    AgentEvaluationRun runEvaluation(Long datasetId, Long userId);

    /**
     * 获取评测执行历史
     */
    List<AgentEvaluationRun> listEvaluationRuns(Long datasetId, int page, int pageSize);

    /**
     * 获取单次评测执行详情
     */
    AgentEvaluationRun getEvaluationRun(Long runId);

    // ── 回归门禁 ──

    /**
     * 检查最新评测结果是否通过回归门禁。
     * 返回门禁检查结果（pass/fail + 各维度详情）。
     */
    Map<String, Object> checkRegressionGate(Long datasetId);

    /**
     * 获取默认回归门禁阈值
     */
    Map<String, Double> getDefaultGateThresholds();
}
