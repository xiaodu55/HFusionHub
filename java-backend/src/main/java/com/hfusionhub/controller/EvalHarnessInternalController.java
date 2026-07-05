package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.InternalTokenGuard;
import com.hfusionhub.dto.EvalCorpusImportResultDTO;
import com.hfusionhub.entity.EvalHarnessRun;
import com.hfusionhub.mapper.EvalHarnessRunMapper;
import com.hfusionhub.service.EvalCorpusImportService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * Internal-only endpoints for the evaluation harness (python-ai → Java).
 * Protected by X-Internal-Token with constant-time comparison.
 * Excluded from Sa-Token login check in SaTokenConfig.
 */
@Hidden
@Slf4j
@RestController
@RequestMapping("/internal/eval-harness")
@RequiredArgsConstructor
@Tag(name = "Internal Eval Harness", description = "Token-protected endpoints for Python AI eval sync")
public class EvalHarnessInternalController {

    private final EvalHarnessRunMapper evalHarnessRunMapper;
    private final EvalCorpusImportService evalCorpusImportService;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;


    /**
     * 记录一次评估运行的聚合摘要（python eval-harness run 完成后回调）。
     * 租户上下文按回调头的 X-Tenant-Id 显式建立（内部通道无登录态）。
     */
    @PostMapping("/record")
    @Operation(summary = "Record eval run summary (internal only)")
    public R<Map<String, Object>> record(
            @RequestHeader(value = "X-Internal-Token", required = false) String providedToken,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "1") String tenantHeader,
            @RequestBody Map<String, Object> body) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, providedToken)) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        long tenantId;
        try {
            tenantId = Long.parseLong(tenantHeader);
        } catch (NumberFormatException e) {
            tenantId = 1L;
        }

        EvalHarnessRun run = new EvalHarnessRun();
        run.setRunFile(String.valueOf(body.getOrDefault("run_file", "")));
        run.setLabel(String.valueOf(body.getOrDefault("label", "")));
        run.setKnowledgeBaseId(toLong(body.get("knowledge_base_id")));
        run.setTopK(toInteger(body.get("top_k"), 5));
        run.setRecordCount(toInteger(body.get("record_count"), 0));
        run.setRequiresRagCount(toInteger(body.get("requires_rag_count"), 0));
        run.setJudgeEnabled(Boolean.TRUE.equals(body.get("judge_enabled")) ? 1 : 0);
        run.setJudgeCases(toInteger(body.get("judge_cases"), 0));
        run.setOverall(toMap(body.get("overall")));
        run.setFailedCaseIds(toMap(body.get("failed_case_ids")));

        TenantContext.runAs(tenantId, () -> evalHarnessRunMapper.insert(run));
        log.info("评估运行摘要已记录: runFile={}, tenant={}, recordCount={}",
                run.getRunFile(), tenantId, run.getRecordCount());
        return R.ok(Map.of("recorded", true, "id", run.getId() == null ? 0 : run.getId()));
    }

    /** 评测语料导入（内部通道供初始化脚本使用；浏览器走 /demo/import-corpus）。 */
    @PostMapping("/import-corpus")
    @Operation(summary = "Import evaluation corpus (internal only)")
    public R<EvalCorpusImportResultDTO> importCorpus(
            @RequestHeader(value = "X-Internal-Token", required = false) String providedToken,
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "1") String tenantHeader,
            @RequestHeader(value = "X-User-Id", defaultValue = "1") String userHeader) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, providedToken)) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        long tenantId;
        long userId;
        try {
            tenantId = Long.parseLong(tenantHeader);
            userId = Long.parseLong(userHeader);
        } catch (NumberFormatException e) {
            tenantId = 1L;
            userId = 1L;
        }
        final long tid = tenantId;
        final long uid = userId;
        return R.ok(TenantContext.runAs(tid, () -> evalCorpusImportService.importCorpus(uid)));
    }

    private Long toLong(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Integer toInteger(Object value, int fallback) {
        if (value instanceof Number number) return number.intValue();
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toMap(Object value) {
        if (value instanceof Map) return (Map<String, Object>) value;
        return Map.of();
    }
}
