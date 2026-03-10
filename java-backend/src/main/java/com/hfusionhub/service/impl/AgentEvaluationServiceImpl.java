package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.AgentEvaluationCase;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.AgentEvaluationRun;
import com.hfusionhub.mapper.AgentEvaluationCaseMapper;
import com.hfusionhub.mapper.AgentEvaluationDatasetMapper;
import com.hfusionhub.mapper.AgentEvaluationRunMapper;
import com.hfusionhub.service.AgentEvaluationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Agent 离线评测集管理与评测执行服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentEvaluationServiceImpl implements AgentEvaluationService {

    private final AgentEvaluationDatasetMapper datasetMapper;
    private final AgentEvaluationCaseMapper caseMapper;
    private final AgentEvaluationRunMapper runMapper;
    private final RestTemplate restTemplate;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String aiServiceBaseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    private static final Map<String, Double> DEFAULT_THRESHOLDS = Map.of(
        "answer_correctness", 0.5,
        "citation_consistency", 0.5,
        "privilege_containment", 0.8,
        "tool_success_rate", 0.8
    );

    // ================================================================
    // 评测集 CRUD
    // ================================================================

    @Override
    @Transactional
    public AgentEvaluationDataset createDataset(AgentEvaluationDataset dataset) {
        dataset.setCaseCount(0);
        dataset.setCreatedAt(LocalDateTime.now());
        dataset.setUpdatedAt(LocalDateTime.now());
        datasetMapper.insert(dataset);
        log.info("Created evaluation dataset: id={} name={}", dataset.getId(), dataset.getName());
        return dataset;
    }

    @Override
    public AgentEvaluationDataset getDataset(Long datasetId) {
        AgentEvaluationDataset ds = datasetMapper.selectById(datasetId);
        if (ds == null) throw new BusinessException("评测集不存在: " + datasetId);
        return ds;
    }

    @Override
    public List<AgentEvaluationDataset> listDatasets(Long userId, Long kbId,
                                                      int page, int pageSize) {
        int offset = (page - 1) * pageSize;
        LambdaQueryWrapper<AgentEvaluationDataset> query = new LambdaQueryWrapper<>();
        if (kbId != null) {
            query.eq(AgentEvaluationDataset::getKnowledgeBaseId, kbId);
        } else if (userId != null) {
            query.eq(AgentEvaluationDataset::getUserId, userId);
        }
        query.orderByDesc(AgentEvaluationDataset::getCreatedAt)
             .last("LIMIT " + offset + "," + pageSize);
        return datasetMapper.selectList(query);
    }

    @Override
    @Transactional
    public void deleteDataset(Long datasetId) {
        AgentEvaluationDataset ds = getDataset(datasetId);
        LambdaQueryWrapper<AgentEvaluationCase> caseQuery = new LambdaQueryWrapper<>();
        caseQuery.eq(AgentEvaluationCase::getDatasetId, datasetId);
        caseMapper.delete(caseQuery);
        datasetMapper.deleteById(datasetId);
        log.info("Deleted evaluation dataset: id={}", datasetId);
    }

    // ================================================================
    // 用例管理
    // ================================================================

    @Override
    @Transactional
    public AgentEvaluationCase addCase(AgentEvaluationCase evalCase) {
        AgentEvaluationDataset ds = getDataset(evalCase.getDatasetId());
        evalCase.setCreatedAt(LocalDateTime.now());
        caseMapper.insert(evalCase);

        // Update case count
        LambdaQueryWrapper<AgentEvaluationCase> countQuery = new LambdaQueryWrapper<>();
        countQuery.eq(AgentEvaluationCase::getDatasetId, evalCase.getDatasetId());
        int count = Math.toIntExact(caseMapper.selectCount(countQuery));
        ds.setCaseCount(count);
        ds.setUpdatedAt(LocalDateTime.now());
        datasetMapper.updateById(ds);

        return evalCase;
    }

    @Override
    public List<AgentEvaluationCase> getCases(Long datasetId) {
        LambdaQueryWrapper<AgentEvaluationCase> query = new LambdaQueryWrapper<>();
        query.eq(AgentEvaluationCase::getDatasetId, datasetId)
             .orderByAsc(AgentEvaluationCase::getId);
        return caseMapper.selectList(query);
    }

    @Override
    @Transactional
    public void deleteCase(Long caseId) {
        AgentEvaluationCase c = caseMapper.selectById(caseId);
        if (c == null) throw new BusinessException("用例不存在: " + caseId);
        caseMapper.deleteById(caseId);

        // Update case count
        AgentEvaluationDataset ds = datasetMapper.selectById(c.getDatasetId());
        if (ds != null) {
            LambdaQueryWrapper<AgentEvaluationCase> countQuery = new LambdaQueryWrapper<>();
            countQuery.eq(AgentEvaluationCase::getDatasetId, c.getDatasetId());
            ds.setCaseCount(Math.toIntExact(caseMapper.selectCount(countQuery)));
            ds.setUpdatedAt(LocalDateTime.now());
            datasetMapper.updateById(ds);
        }
    }

    // ================================================================
    // 评测执行
    // ================================================================

    @Override
    @Transactional
    public AgentEvaluationRun runEvaluation(Long datasetId, Long userId) {
        AgentEvaluationDataset ds = getDataset(datasetId);
        List<AgentEvaluationCase> cases = getCases(datasetId);

        if (cases.isEmpty()) {
            throw new BusinessException("评测集没有用例，无法执行评测");
        }

        String runUuid = UUID.randomUUID().toString();

        // Create run record
        AgentEvaluationRun run = new AgentEvaluationRun();
        run.setDatasetId(datasetId);
        run.setRunUuid(runUuid);
        run.setStatus("running");
        run.setCreatedAt(LocalDateTime.now());
        runMapper.insert(run);

        // Build request for Python — only send query + ground truth.
        // Python will invoke the real Agent to get actual answer/sources/tool_calls.
        List<Map<String, Object>> caseRequests = cases.stream().map(c -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("case_id", String.valueOf(c.getId()));
            item.put("query", c.getQuery() != null ? c.getQuery() : "");
            // ground_truth = expectedAnswer (used for scoring, NOT as fake answer)
            if (c.getExpectedAnswer() != null) item.put("ground_truth", c.getExpectedAnswer());
            if (c.getExpectedSources() != null) item.put("expected_document_ids", c.getExpectedSources());
            if (c.getPrivilegeTest() != null) item.put("privilege_test", c.getPrivilegeTest());
            if (c.getMetadata() != null) item.put("metadata", c.getMetadata());
            item.put("user_id", userId);
            return item;
        }).collect(Collectors.toList());

        Map<String, Object> requestBody = new LinkedHashMap<>();
        requestBody.put("knowledge_base_id", ds.getKnowledgeBaseId());
        requestBody.put("user_id", userId);
        requestBody.put("label", "dataset_" + ds.getId() + "_" + runUuid.substring(0, 8));
        requestBody.put("dimensions", ds.getDimensions() != null ? ds.getDimensions()
                : List.of("answer_correctness", "citation_consistency", "privilege_containment", "tool_success_rate"));
        requestBody.put("cases", caseRequests);

        // Call Python
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set("X-Internal-Token", internalApiToken);

            @SuppressWarnings("unchecked")
            Map<String, Object> pythonResponse = restTemplate.postForObject(
                    aiServiceBaseUrl + "/api/agent/observability/evaluate/run",
                    new HttpEntity<>(requestBody, headers),
                    Map.class
            );

            // Update run record
            if (pythonResponse != null) {
                Object overallObj = pythonResponse.get("overall_score");
                Double overallScore = overallObj instanceof Number n ? n.doubleValue() : null;
                run.setOverallScore(overallScore);

                @SuppressWarnings("unchecked")
                Map<String, Object> dimScores = (Map<String, Object>) pythonResponse.get("dimension_scores");
                run.setDimensionScores(dimScores);

                // Build rich caseResults: summary + per-case details (real answer, sources, scores)
                @SuppressWarnings("unchecked")
                Map<String, Object> summary = (Map<String, Object>) pythonResponse.get("summary");
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> casesDetail = (List<Map<String, Object>>) pythonResponse.get("cases");

                Map<String, Object> richCaseResults = new LinkedHashMap<>();
                if (summary != null) richCaseResults.put("summary", summary);
                if (casesDetail != null) richCaseResults.put("cases", casesDetail);
                run.setCaseResults(richCaseResults);

                @SuppressWarnings("unchecked")
                List<String> failedIds = (List<String>) pythonResponse.get("failed_case_ids");
                run.setFailedCaseIds(failedIds);

                @SuppressWarnings("unchecked")
                Map<String, Object> gate = (Map<String, Object>) pythonResponse.get("regression_gate");
                if (gate != null) {
                    Object passed = gate.get("passed");
                    run.setStatus(Boolean.TRUE.equals(passed) ? "completed" : "completed");
                } else {
                    run.setStatus("completed");
                }
            }
        } catch (Exception e) {
            log.error("Evaluation run failed for dataset {}: {}", datasetId, e.getMessage());
            run.setStatus("failed");
            run.setErrorDetail(e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        runMapper.updateById(run);
        log.info("Evaluation run {} completed: status={} score={}",
                runUuid, run.getStatus(), run.getOverallScore());
        return run;
    }

    @Override
    public List<AgentEvaluationRun> listEvaluationRuns(Long datasetId, int page, int pageSize) {
        int offset = (page - 1) * pageSize;
        LambdaQueryWrapper<AgentEvaluationRun> query = new LambdaQueryWrapper<>();
        query.eq(AgentEvaluationRun::getDatasetId, datasetId)
             .orderByDesc(AgentEvaluationRun::getCreatedAt)
             .last("LIMIT " + offset + "," + pageSize);
        return runMapper.selectList(query);
    }

    @Override
    public AgentEvaluationRun getEvaluationRun(Long runId) {
        return runMapper.selectById(runId);
    }

    // ================================================================
    // 回归门禁
    // ================================================================

    @Override
    public Map<String, Object> checkRegressionGate(Long datasetId) {
        // Get latest evaluation run for this dataset
        LambdaQueryWrapper<AgentEvaluationRun> query = new LambdaQueryWrapper<>();
        query.eq(AgentEvaluationRun::getDatasetId, datasetId)
             .orderByDesc(AgentEvaluationRun::getCreatedAt)
             .last("LIMIT 1");
        List<AgentEvaluationRun> runs = runMapper.selectList(query);
        if (runs.isEmpty()) {
            return Map.of(
                "passed", false,
                "message", "No evaluation runs found for this dataset",
                "dimensions", Map.of(),
                "scores", Map.of(),
                "thresholds", DEFAULT_THRESHOLDS
            );
        }

        AgentEvaluationRun latest = runs.get(0);
        Map<String, Object> dimScores = latest.getDimensionScores();
        if (dimScores == null) dimScores = Map.of();

        Map<String, Boolean> dimResults = new LinkedHashMap<>();
        Map<String, Double> dimScoreValues = new LinkedHashMap<>();
        List<String> failed = new ArrayList<>();

        for (var entry : DEFAULT_THRESHOLDS.entrySet()) {
            String dim = entry.getKey();
            double threshold = entry.getValue();
            Object scoreObj = dimScores.get(dim);
            double score = scoreObj instanceof Number n ? n.doubleValue() : 0.0;
            dimScoreValues.put(dim, score);
            boolean pass = score >= threshold;
            dimResults.put(dim, pass);
            if (!pass) failed.add(dim);
        }

        boolean allPassed = failed.isEmpty();
        return Map.of(
            "passed", allPassed,
            "message", allPassed ? "All quality gates passed."
                    : "Failed dimensions: " + String.join(", ", failed),
            "dimensions", dimResults,
            "scores", dimScoreValues,
            "thresholds", DEFAULT_THRESHOLDS,
            "failed_dimensions", failed,
            "evaluation_run_id", latest.getRunUuid()
        );
    }

    @Override
    public Map<String, Double> getDefaultGateThresholds() {
        return DEFAULT_THRESHOLDS;
    }
}
