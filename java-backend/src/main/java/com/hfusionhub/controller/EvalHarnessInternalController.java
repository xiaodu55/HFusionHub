package com.hfusionhub.controller;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
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
 *
 * <p>Rejections (bad token, missing/invalid tenant) are thrown as
 * {@link BusinessException} so {@code GlobalExceptionHandler} maps them onto a real
 * HTTP 403 — python-ai's callback only inspects the status code, so an
 * {@code R.fail(403)} carried over HTTP 200 would be logged as a successful record.</p>
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
     * 租户上下文按回调头的 X-Tenant-Id 显式建立（内部通道无登录态），缺头即拒绝。
     */
    @PostMapping("/record")
    @Operation(summary = "Record eval run summary (internal only)")
    public R<Map<String, Object>> record(
            @RequestHeader(value = "X-Internal-Token", required = false) String providedToken,
            @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
            @RequestBody Map<String, Object> body) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, providedToken)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "Forbidden: invalid or missing X-Internal-Token");
        }
        long tenantId = requirePositiveId(tenantHeader, "X-Tenant-Id");

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

    /** 评测语料导入（内部通道供初始化脚本使用；浏览器走 /demo/import-corpus）。租户与归属用户均须显式给出。 */
    @PostMapping("/import-corpus")
    @Operation(summary = "Import evaluation corpus (internal only)")
    public R<EvalCorpusImportResultDTO> importCorpus(
            @RequestHeader(value = "X-Internal-Token", required = false) String providedToken,
            @RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
            @RequestHeader(value = "X-User-Id", required = false) String userHeader) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, providedToken)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "Forbidden: invalid or missing X-Internal-Token");
        }
        long tenantId = requirePositiveId(tenantHeader, "X-Tenant-Id");
        long userId = requirePositiveId(userHeader, "X-User-Id");
        return R.ok(TenantContext.runAs(tenantId, () -> evalCorpusImportService.importCorpus(userId)));
    }

    /**
     * 内部通道没有登录态，也没有租户拦截器兜底，头里的租户/用户是唯一的归属依据：
     * 缺省或解析失败必须拒绝（403，与 {@code TenantContextInterceptor.rejectNoTenant}
     * 及本类的令牌守卫同档），不能回落成 tenant 1 —— 那会把一个租户的数据记到另一个租户名下。
     */
    private static long requirePositiveId(String headerValue, String headerName) {
        String raw = headerValue == null ? "" : headerValue.strip();
        long parsed;
        try {
            parsed = Long.parseLong(raw);
        } catch (NumberFormatException e) {
            throw new BusinessException(
                    StatusCode.FORBIDDEN, "Missing or invalid " + headerName + " header: '" + raw + "'");
        }
        if (parsed < 1) {
            throw new BusinessException(
                    StatusCode.FORBIDDEN, headerName + " header must be a positive id: '" + raw + "'");
        }
        return parsed;
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
