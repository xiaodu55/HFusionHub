package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.PromptTestSetRunStatus;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTestCaseComparison;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseResult;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetCompareRequest;
import com.hfusionhub.dto.PromptTestSetCompareResponse;
import com.hfusionhub.dto.PromptTestSetDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDTO;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunStatusDTO;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.PromptTestCase;
import com.hfusionhub.entity.PromptTestCaseResultEntity;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.PromptTestSet;
import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.PromptTestCaseMapper;
import com.hfusionhub.mapper.PromptTestCaseResultMapper;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.PromptTestSetMapper;
import com.hfusionhub.mapper.PromptTestSetRunMapper;
import com.hfusionhub.service.PromptTestSetService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.UUID;

/** 提示词测试用例集服务实现。 */
@Slf4j
@Service
public class PromptTestSetServiceImpl implements PromptTestSetService {

    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{\\s*([\\p{L}\\p{N}_.]+)\\s*}}");

    private final PromptTestSetMapper testSetMapper;
    private final PromptTestCaseMapper testCaseMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final PromptTemplateMapper promptTemplateMapper;
    private final AiClient aiClient;
    private final PromptTestSetRunMapper runMapper;
    private final PromptTestCaseResultMapper caseResultMapper;
    private final PromptTestSetCaseWriter caseWriter;

    /** 单个用例失败后的重试总尝试次数（含首次） */
    private final int caseRetryMaxAttempts;

    /** 用例重试间隔（毫秒），0 表示不等待 */
    private final long caseRetryDelayMs;

    /** 已请求取消的 Run（runId → true），供 Worker 在用例边界检查 */
    private final ConcurrentHashMap<Long, Boolean> cancelledRuns = new ConcurrentHashMap<>();

    public PromptTestSetServiceImpl(
            PromptTestSetMapper testSetMapper,
            PromptTestCaseMapper testCaseMapper,
            KnowledgeBaseMapper knowledgeBaseMapper,
            PromptTemplateMapper promptTemplateMapper,
            AiClient aiClient,
            PromptTestSetRunMapper runMapper,
            PromptTestCaseResultMapper caseResultMapper,
            PromptTestSetCaseWriter caseWriter,
            @Value("${prompt-test-set.run.case-retry-max-attempts:2}") int caseRetryMaxAttempts,
            @Value("${prompt-test-set.run.case-retry-delay-ms:500}") long caseRetryDelayMs) {
        this.testSetMapper = testSetMapper;
        this.testCaseMapper = testCaseMapper;
        this.knowledgeBaseMapper = knowledgeBaseMapper;
        this.promptTemplateMapper = promptTemplateMapper;
        this.aiClient = aiClient;
        this.runMapper = runMapper;
        this.caseResultMapper = caseResultMapper;
        this.caseWriter = caseWriter;
        this.caseRetryMaxAttempts = Math.max(1, caseRetryMaxAttempts);
        this.caseRetryDelayMs = Math.max(0, caseRetryDelayMs);
    }

    // ── CRUD ──────────────────────────────────────────────────────────

    @Override
    public List<PromptTestSetDTO> listMine() {
        Long userId = JwtUtils.getCurrentUserId();
        return testSetMapper.selectList(new LambdaQueryWrapper<PromptTestSet>()
                        .eq(PromptTestSet::getUserId, userId)
                        .orderByDesc(PromptTestSet::getUpdatedAt))
                .stream().map(this::toSetDTO).toList();
    }

    @Override
    @Transactional
    public PromptTestSetDetailDTO create(PromptTestSetSaveDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        ensureNameAvailable(dto.getName(), userId, null);
        PromptTestSet set = new PromptTestSet();
        set.setUserId(userId);
        set.setName(dto.getName().trim());
        set.setDescription(clean(dto.getDescription()));
        testSetMapper.insert(set);
        return toDetail(set, List.of());
    }

    @Override
    public PromptTestSetDetailDTO getDetail(Long id) {
        PromptTestSet set = requireOwned(id, JwtUtils.getCurrentUserId());
        return toDetail(set, listCases(id));
    }

    @Override
    @Transactional
    public PromptTestSetDetailDTO update(Long id, PromptTestSetSaveDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        PromptTestSet set = requireOwned(id, userId);
        ensureNameAvailable(dto.getName(), userId, id);
        set.setName(dto.getName().trim());
        set.setDescription(clean(dto.getDescription()));
        testSetMapper.updateById(set);
        return toDetail(set, listCases(id));
    }

    @Override
    @Transactional
    public void delete(Long id) {
        requireOwned(id, JwtUtils.getCurrentUserId());
        testCaseMapper.delete(new LambdaQueryWrapper<PromptTestCase>()
                .eq(PromptTestCase::getSetId, id));
        testSetMapper.deleteById(id);
    }

    // ── Cases ─────────────────────────────────────────────────────────

    @Override
    @Transactional
    public PromptTestCaseDTO addCase(Long setId, PromptTestCaseSaveDTO dto) {
        requireOwned(setId, JwtUtils.getCurrentUserId());
        PromptTestCase tc = new PromptTestCase();
        tc.setSetId(setId);
        tc.setQuestion(dto.getQuestion().trim());
        tc.setVariables(emptyToNull(dto.getVariables()));
        tc.setExpectedKeywords(emptyToNullList(dto.getExpectedKeywords()));
        tc.setRequiredDocumentIds(emptyToNullList(dto.getRequiredDocumentIds()));
        tc.setSortOrder(dto.getSortOrder() != null ? dto.getSortOrder() : nextSortOrder(setId));
        testCaseMapper.insert(tc);
        return toCaseDTO(tc);
    }

    @Override
    @Transactional
    public PromptTestCaseDTO updateCase(Long setId, Long caseId, PromptTestCaseSaveDTO dto) {
        requireOwned(setId, JwtUtils.getCurrentUserId());
        PromptTestCase tc = requireCaseInSet(caseId, setId);
        tc.setQuestion(dto.getQuestion().trim());
        tc.setVariables(emptyToNull(dto.getVariables()));
        tc.setExpectedKeywords(emptyToNullList(dto.getExpectedKeywords()));
        tc.setRequiredDocumentIds(emptyToNullList(dto.getRequiredDocumentIds()));
        if (dto.getSortOrder() != null) tc.setSortOrder(dto.getSortOrder());
        testCaseMapper.updateById(tc);
        return toCaseDTO(tc);
    }

    @Override
    @Transactional
    public void deleteCase(Long setId, Long caseId) {
        requireOwned(setId, JwtUtils.getCurrentUserId());
        requireCaseInSet(caseId, setId);
        testCaseMapper.deleteById(caseId);
    }

    // ── Batch run ─────────────────────────────────────────────────────

    /**
     * 提交一次批量运行：校验所有权与模板快照后，写入 pending 运行记录并立即返回，
     * 实际执行由后台 Worker（排队）或测试中的 {@link #executeRun} 完成。
     */
    @Override
    @Transactional
    public PromptTestSetRunStatusDTO run(Long setId, PromptTestSetRunRequest request) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        PromptTestSet set = requireOwned(setId, currentUserId);
        List<PromptTestCase> cases = listCases(setId);
        if (cases.isEmpty()) {
            throw new BusinessException("用例集为空，请先添加测试用例");
        }

        // KB ownership validation (if specified)
        if (request.getKnowledgeBaseId() != null && request.getKnowledgeBaseId() > 0) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(request.getKnowledgeBaseId());
            if (kb == null) {
                throw new BusinessException("知识库不存在");
            }
            if (!kb.getUserId().equals(currentUserId)) {
                throw new BusinessException("无权访问该知识库");
            }
        }

        // Resolve bound template from DB (ownership + real snapshot). Forged/foreign templates rejected.
        PromptTestSetRunRequest resolved = resolveTemplateSnapshot(request, currentUserId);

        PromptTestSetRun run = new PromptTestSetRun();
        run.setSetId(set.getId());
        run.setUserId(currentUserId);
        run.setTemplateId(resolved.getTemplateId());
        run.setTemplateVersion(resolved.getTemplateVersion());
        run.setTemplateName(clean(resolved.getTemplateName()));
        run.setTemplateContent(resolved.getTemplateContent());
        run.setKnowledgeBaseId(resolved.getKnowledgeBaseId());
        run.setTotalCases(cases.size());
        run.setStatus(PromptTestSetRunStatus.PENDING);
        run.setAttemptNumber(1);
        run.setProgressCount(0);
        run.setExecutionToken(UUID.randomUUID().toString());
        run.setScheduledAt(LocalDateTime.now());
        runMapper.insert(run);

        log.info("Prompt test set run queued: setId={} runId={} cases={}", setId, run.getId(), cases.size());
        return toStatusDTO(run);
    }

    /**
     * Worker 执行主体：从 pending/running 开始逐用例运行并增量持久化结果，
     * 期间检查取消标志并在每个用例完成后更新进度；结束后收敛到终态。
     * 幂等：已处于终态的 Run 直接返回。
     *
     * <p>并发隔离：本方法捕获执行开始时的 {@code executionToken}。每次写入
     * （进度推进、结果持久化、终态收敛）前都以「token + 活跃状态」为条件做
     * 守卫更新；一旦该 Run 被取消后立即重试（token 重新生成）或由另一实例
     * 收敛（状态离开活跃集合），守卫更新将命中 0 行，本 Worker 立即中止，
     * 不会把结果写入新一轮任务。
     */
    @Override
    public PromptTestSetRunResponse executeRun(Long runId) {
        PromptTestSetRun run = runMapper.selectById(runId);
        if (run == null) {
            log.warn("Prompt test set run {} not found", runId);
            return null;
        }
        if (!PromptTestSetRunStatus.PENDING.equals(run.getStatus())
                && !PromptTestSetRunStatus.RUNNING.equals(run.getStatus())) {
            log.debug("Run {} already terminal: status={}", runId, run.getStatus());
            return null;
        }
        // 捕获本次执行的乐观锁令牌：retry 会重新生成，从而让残留的旧 Worker 失效。
        String token = run.getExecutionToken();

        PromptTestSet set = testSetMapper.selectById(run.getSetId());
        if (set == null) {
            finalizeRun(run, 0, 0, 0, PromptTestSetRunStatus.FAILED, "用例集不存在或已删除");
            return null;
        }

        List<PromptTestCase> cases = listCases(run.getSetId());
        if (cases.isEmpty()) {
            finalizeRun(run, 0, 0, 0, PromptTestSetRunStatus.FAILED, "用例集为空，无法执行");
            return null;
        }

        PromptTestSetRunRequest request = snapshotRequest(run);
        long start = System.currentTimeMillis();
        int success = 0;
        int pass = 0;
        int progress = 0;
        List<PromptTestCaseResult> results = new ArrayList<>(cases.size());

        for (PromptTestCase tc : cases) {
            if (isCancelled(runId)) {
                log.info("Run {} cancelled — stopping before case {}", runId, tc.getId());
                cancelRunInternal(run);
                long totalElapsed = System.currentTimeMillis() - start;
                return buildResponse(set, run, cases.size(), success, pass, totalElapsed, results);
            }
            PromptTestCaseResult r = runSingleWithRetry(set, tc, request, run.getUserId());
            // 原子写：token 校验 + 进度更新 + 结果插入在单个数据库事务内完成。
            // 若 run 已被取消→重试（token 重新生成）或由另一实例收敛，守卫更新命中
            // 0 行，事务不写入任何结果——旧 Worker 立即中止，不残留脏数据。
            boolean persisted = caseWriter.persistCase(run, token, progress + 1, r);
            if (!persisted) {
                log.info("Run {} stale (execution token changed) — worker aborts without persisting case {}",
                        runId, tc.getId());
                return null;
            }
            results.add(r);
            if (r.isSuccess()) success++;
            if (r.isPassed()) pass++;
            progress++;
        }

        long totalElapsed = System.currentTimeMillis() - start;
        finalizeRun(run, success, pass, totalElapsed, PromptTestSetRunStatus.SUCCEEDED, null);
        log.info("Prompt test set run completed: runId={} success={} fail={} pass={} elapsed={}ms",
                runId, success, cases.size() - success, pass, totalElapsed);
        return buildResponse(set, run, cases.size(), success, pass, totalElapsed, results);
    }

    @Override
    public PromptTestSetRunStatusDTO getRunStatus(Long runId) {
        PromptTestSetRun run = requireOwnedRun(runId, JwtUtils.getCurrentUserId());
        return toStatusDTO(run);
    }

    @Override
    public PromptTestSetRunStatusDTO cancelRun(Long runId) {
        PromptTestSetRun run = requireOwnedRun(runId, JwtUtils.getCurrentUserId());
        if (PromptTestSetRunStatus.TERMINAL_STATUSES.contains(run.getStatus())) {
            return toStatusDTO(run);
        }
        cancelledRuns.put(runId, Boolean.TRUE);
        cancelRunInternal(run);
        log.info("Prompt test set run {} cancelled by user {}", runId, JwtUtils.getCurrentUserId());
        return toStatusDTO(runMapper.selectById(runId));
    }

    @Override
    @Transactional
    public PromptTestSetRunStatusDTO retryRun(Long runId) {
        PromptTestSetRun run = requireOwnedRun(runId, JwtUtils.getCurrentUserId());
        if (!PromptTestSetRunStatus.TERMINAL_STATUSES.contains(run.getStatus())) {
            throw new BusinessException("运行尚未结束，无法重试");
        }
        if (PromptTestSetRunStatus.SUCCEEDED.equals(run.getStatus()) && run.getFailureCount() == 0) {
            throw new BusinessException("运行已成功且无失败用例，无需重试");
        }
        // Re-queue: drop previous results, reset to pending with next attempt.
        // 重新生成 executionToken：任何存活中的旧 Worker 将因 token 不匹配而在下一次
        // 守卫写入时失效，从根源上隔离取消后立即重试造成的串扰。
        String newToken = UUID.randomUUID().toString();
        caseResultMapper.delete(new LambdaQueryWrapper<PromptTestCaseResultEntity>()
                .eq(PromptTestCaseResultEntity::getRunId, runId));
        cancelledRuns.remove(runId);
        runMapper.update(null, new LambdaUpdateWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getId, runId)
                .set(PromptTestSetRun::getStatus, PromptTestSetRunStatus.PENDING)
                .set(PromptTestSetRun::getAttemptNumber, run.getAttemptNumber() + 1)
                .set(PromptTestSetRun::getProgressCount, 0)
                .set(PromptTestSetRun::getSuccessCount, 0)
                .set(PromptTestSetRun::getFailureCount, 0)
                .set(PromptTestSetRun::getPassCount, 0)
                .set(PromptTestSetRun::getTotalElapsedMs, 0)
                .set(PromptTestSetRun::getExecutionToken, newToken)
                .set(PromptTestSetRun::getErrorMessage, null)
                .set(PromptTestSetRun::getScheduledAt, LocalDateTime.now())
                .set(PromptTestSetRun::getStartedAt, null)
                .set(PromptTestSetRun::getHeartbeatAt, null)
                .set(PromptTestSetRun::getCompletedAt, null));
        PromptTestSetRun fresh = runMapper.selectById(runId);
        log.info("Prompt test set run {} re-queued for retry (attempt {})", runId, fresh.getAttemptNumber());
        return toStatusDTO(fresh);
    }

    // ── Queue mechanics (used by the worker scheduler) ────────────────

    @Override
    public List<PromptTestSetRun> listQueuedRuns(int limit) {
        return runMapper.selectList(new LambdaQueryWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getStatus, PromptTestSetRunStatus.PENDING)
                .and(w -> w.isNull(PromptTestSetRun::getScheduledAt).or()
                        .le(PromptTestSetRun::getScheduledAt, LocalDateTime.now()))
                .orderByAsc(PromptTestSetRun::getId)
                .last("LIMIT " + Math.max(1, limit)));
    }

    @Override
    public boolean claimRun(Long runId) {
        LocalDateTime now = LocalDateTime.now();
        return runMapper.update(null, new LambdaUpdateWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getId, runId)
                .eq(PromptTestSetRun::getStatus, PromptTestSetRunStatus.PENDING)
                .set(PromptTestSetRun::getStatus, PromptTestSetRunStatus.RUNNING)
                .set(PromptTestSetRun::getStartedAt, now)
                .set(PromptTestSetRun::getHeartbeatAt, now)) > 0;
    }

    @Override
    public int markStaleRunsFailed(long staleMinutes) {
        LocalDateTime threshold = LocalDateTime.now().minusMinutes(staleMinutes);
        // 失联判断改为基于心跳：正常运行每处理一个用例都会刷新 heartbeat_at，
        // 只有「最近一次心跳超过 threshold」或「从未处理过用例（heartbeat 为空）
        // 且 startedAt 超过 threshold」的 running 运行才视为失联。
        List<PromptTestSetRun> stale = runMapper.selectList(new LambdaQueryWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getStatus, PromptTestSetRunStatus.RUNNING)
                .and(w -> w.isNull(PromptTestSetRun::getHeartbeatAt).and(q -> q.lt(PromptTestSetRun::getStartedAt, threshold))
                        .or().lt(PromptTestSetRun::getHeartbeatAt, threshold)));
        int marked = 0;
        for (PromptTestSetRun run : stale) {
            try {
                finalizeRun(run, 0, 0, 0, PromptTestSetRunStatus.FAILED,
                        "执行超时：超过 " + staleMinutes + " 分钟无心跳");
                marked++;
            } catch (Exception e) {
                log.warn("Failed to mark stale run {} failed: {}", run.getId(), e.getMessage());
            }
        }
        if (marked > 0) {
            log.warn("Recovery marked {} stale prompt test set runs as failed", marked);
        }
        return marked;
    }

    // ── Run execution internals ───────────────────────────────────────

    /** 单个用例执行，失败时按配置重试（默认最多 2 次尝试）。 */
    private PromptTestCaseResult runSingleWithRetry(PromptTestSet set, PromptTestCase tc,
                                                    PromptTestSetRunRequest request, Long userId) {
        PromptTestCaseResult last = null;
        for (int attempt = 1; attempt <= caseRetryMaxAttempts; attempt++) {
            if (attempt > 1 && caseRetryDelayMs > 0) {
                try {
                    Thread.sleep(caseRetryDelayMs);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            last = runSingle(set, tc, request, userId);
            if (last.isSuccess()) return last;
        }
        if (last != null && !last.isSuccess() && caseRetryMaxAttempts > 1) {
            log.debug("Case {} exhausted {} attempts", tc.getId(), caseRetryMaxAttempts);
        }
        return last;
    }

    private PromptTestSetRunRequest snapshotRequest(PromptTestSetRun run) {
        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setKnowledgeBaseId(run.getKnowledgeBaseId());
        request.setTemplateContent(run.getTemplateContent());
        request.setTemplateId(run.getTemplateId());
        request.setTemplateVersion(run.getTemplateVersion());
        request.setTemplateName(run.getTemplateName());
        return request;
    }

    private boolean isCancelled(Long runId) {
        return Boolean.TRUE.equals(cancelledRuns.get(runId));
    }

    /** 收敛到终态（幂等：仅当 token 匹配且当前处于 pending/running 时生效）。 */
    private void finalizeRun(PromptTestSetRun run, int success, int pass, long totalElapsed,
                             String status, String error) {
        run.setStatus(status);
        run.setSuccessCount(success);
        run.setFailureCount(run.getTotalCases() - success);
        run.setPassCount(pass);
        run.setTotalElapsedMs(totalElapsed);
        run.setErrorMessage(error);
        run.setCompletedAt(LocalDateTime.now());
        runMapper.update(null, PromptTestSetRunGuards.activeRunGuard(run.getId(), run.getExecutionToken())
                .set(PromptTestSetRun::getStatus, status)
                .set(PromptTestSetRun::getSuccessCount, success)
                .set(PromptTestSetRun::getFailureCount, run.getTotalCases() - success)
                .set(PromptTestSetRun::getPassCount, pass)
                .set(PromptTestSetRun::getTotalElapsedMs, totalElapsed)
                .set(PromptTestSetRun::getErrorMessage, error)
                .set(PromptTestSetRun::getCompletedAt, run.getCompletedAt()));
    }

    private void cancelRunInternal(PromptTestSetRun run) {
        run.setStatus(PromptTestSetRunStatus.CANCELLED);
        run.setCompletedAt(LocalDateTime.now());
        runMapper.update(null, PromptTestSetRunGuards.activeRunGuard(run.getId(), run.getExecutionToken())
                .set(PromptTestSetRun::getStatus, PromptTestSetRunStatus.CANCELLED)
                .set(PromptTestSetRun::getCompletedAt, run.getCompletedAt()));
    }

    private PromptTestSetRunResponse buildResponse(PromptTestSet set, PromptTestSetRun run,
                                                   int totalCases, int success, int pass,
                                                   long totalElapsed, List<PromptTestCaseResult> results) {
        return PromptTestSetRunResponse.builder()
                .setId(set.getId())
                .runId(run.getId())
                .status(run.getStatus())
                .templateId(run.getTemplateId())
                .templateVersion(run.getTemplateVersion())
                .templateName(run.getTemplateName())
                .totalCases(totalCases)
                .successCount(success)
                .failureCount(totalCases - success)
                .passCount(pass)
                .passRate(computePassRate(pass, totalCases))
                .totalElapsedMs(totalElapsed)
                .results(results)
                .build();
    }

    /** 绑定模板时按当前用户校验并从数据库读取真实模板名称、版本与内容快照；
     * 未绑定（自定义模板）时清除模板关联，历史标记为自定义模板。 */
    private PromptTestSetRunRequest resolveTemplateSnapshot(PromptTestSetRunRequest request, Long userId) {
        PromptTestSetRunRequest resolved = new PromptTestSetRunRequest();
        resolved.setKnowledgeBaseId(request.getKnowledgeBaseId());
        resolved.setTemplateContent(request.getTemplateContent());
        resolved.setTemplateId(null);
        resolved.setTemplateVersion(null);
        resolved.setTemplateName(null);

        Long templateId = request.getTemplateId();
        if (templateId != null && templateId > 0) {
            PromptTemplate template = promptTemplateMapper.selectById(templateId);
            if (template == null) {
                throw new BusinessException("提示词模板不存在");
            }
            if (!userId.equals(template.getUserId())) {
                throw new BusinessException("无权使用该提示词模板");
            }
            resolved.setTemplateId(template.getId());
            resolved.setTemplateVersion(template.getVersion());
            resolved.setTemplateName(template.getName());
            resolved.setTemplateContent(template.getContent());
        } else if (!StringUtils.hasText(request.getTemplateContent())) {
            throw new BusinessException("模板内容不能为空");
        }
        return resolved;
    }

    private PromptTestCaseResult runSingle(PromptTestSet set, PromptTestCase tc,
                                           PromptTestSetRunRequest request, Long userId) {
        long caseStart = System.currentTimeMillis();
        String rendered = renderTemplate(request.getTemplateContent(), tc.getVariables());
        try {
            AiClient.ChatResponse aiResponse;
            if (request.getKnowledgeBaseId() != null && request.getKnowledgeBaseId() > 0) {
                aiResponse = aiClient.agentV1Chat(
                        tc.getQuestion(), null, request.getKnowledgeBaseId(), List.of(),
                        rendered, "detailed", 5, null, userId);
            } else {
                aiResponse = aiClient.chat(
                        tc.getQuestion(), null, null, List.of(), rendered);
            }
            PromptTestCaseResult result = PromptTestCaseResult.builder()
                    .caseId(tc.getId())
                    .question(tc.getQuestion())
                    .renderedTemplate(rendered)
                    .content(aiResponse.getContent() != null ? aiResponse.getContent() : aiResponse.getAnswer())
                    .model(aiResponse.getModel())
                    .tokenCount(aiResponse.getTokenCount())
                    .tokenUsage(aiResponse.getTokenUsage())
                    .sources(aiResponse.getSources())
                    .elapsedMs(System.currentTimeMillis() - caseStart)
                    .success(true)
                    .build();
            return evaluatePassRules(tc, result);
        } catch (Exception e) {
            log.warn("批量运行单个用例失败: setId={}, caseId={}: {}", set.getId(), tc.getId(), e.getMessage());
            return PromptTestCaseResult.builder()
                    .caseId(tc.getId())
                    .question(tc.getQuestion())
                    .renderedTemplate(rendered)
                    .elapsedMs(System.currentTimeMillis() - caseStart)
                    .success(false)
                    .passed(false)
                    .passNotes(List.of("运行失败: " + e.getMessage()))
                    .error(e.getMessage())
                    .build();
        }
    }

    /**
     * 按通过规则评估用例结果：期望关键词须全部出现在回答中（不区分大小写），
     * 必须引用的文档须全部出现在 sources 中。未配置规则时 passed 等于 success。
     */
    private PromptTestCaseResult evaluatePassRules(PromptTestCase tc, PromptTestCaseResult result) {
        if (result.getContent() == null) {
            result.setPassed(false);
            result.setPassNotes(List.of("回答为空"));
            return result;
        }
        List<String> notes = new ArrayList<>();
        boolean passed = true;

        List<String> keywords = tc.getExpectedKeywords();
        if (keywords != null && !keywords.isEmpty()) {
            String lower = result.getContent().toLowerCase();
            for (String kw : keywords) {
                if (kw == null || kw.isBlank()) continue;
                if (!lower.contains(kw.toLowerCase())) {
                    passed = false;
                    notes.add("缺少关键词: " + kw);
                }
            }
        }

        List<Long> requiredDocs = tc.getRequiredDocumentIds();
        if (requiredDocs != null && !requiredDocs.isEmpty()) {
            Set<String> cited = new HashSet<>();
            if (result.getSources() != null) {
                for (Map<String, Object> src : result.getSources()) {
                    Object docId = src.get("document_id");
                    if (docId != null) cited.add(String.valueOf(docId));
                }
            }
            for (Long docId : requiredDocs) {
                if (!cited.contains(String.valueOf(docId))) {
                    passed = false;
                    notes.add("未引用文档: " + docId);
                }
            }
        }

        result.setPassed(passed);
        result.setPassNotes(notes.isEmpty() ? null : notes);
        return result;
    }

    private double computePassRate(int pass, int total) {
        if (total <= 0) return 0;
        return Math.round(pass * 1000.0 / total) / 10.0;
    }

    /** 将模板中的 {{var}} 替换为用例变量值，未提供变量的占位符原样保留。 */
    private String renderTemplate(String template, Map<String, Object> variables) {
        if (template == null || variables == null || variables.isEmpty()) {
            return template;
        }
        Matcher m = VARIABLE_PATTERN.matcher(template);
        StringBuilder sb = new StringBuilder();
        while (m.find()) {
            Object value = variables.get(m.group(1));
            if (value != null) {
                m.appendReplacement(sb, Matcher.quoteReplacement(String.valueOf(value)));
            }
        }
        m.appendTail(sb);
        return sb.toString();
    }

    // ── Run history & comparison ──────────────────────────────────────

    @Override
    public List<PromptTestSetRunDTO> listRuns(Long setId) {
        requireOwned(setId, JwtUtils.getCurrentUserId());
        return runMapper.selectList(new LambdaQueryWrapper<PromptTestSetRun>()
                        .eq(PromptTestSetRun::getSetId, setId)
                        .orderByDesc(PromptTestSetRun::getCreatedAt)
                        .orderByDesc(PromptTestSetRun::getId))
                .stream().map(this::toRunDTO).toList();
    }

    @Override
    public PromptTestSetRunDetailDTO getRunDetail(Long runId) {
        PromptTestSetRun run = requireOwnedRun(runId, JwtUtils.getCurrentUserId());
        LambdaQueryWrapper<PromptTestCaseResultEntity> query = new LambdaQueryWrapper<PromptTestCaseResultEntity>()
                .eq(PromptTestCaseResultEntity::getRunId, runId)
                .orderByAsc(PromptTestCaseResultEntity::getId);
        if (run.getExecutionToken() != null) {
            // 只展示当前 attempt 的结果，隔离任何残留旧 Worker 写入的脏行。
            query.eq(PromptTestCaseResultEntity::getExecutionToken, run.getExecutionToken());
        }
        List<PromptTestCaseResultEntity> entities = caseResultMapper.selectList(query);
        List<PromptTestCaseResult> results = entities.stream().map(this::toCaseResultDTO).toList();
        return PromptTestSetRunDetailDTO.builder()
                .run(toRunDTO(run))
                .results(results)
                .build();
    }

    @Override
    public PromptTestSetCompareResponse compare(PromptTestSetCompareRequest request) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        PromptTestSetRun runA = requireOwnedRun(request.getRunIdA(), currentUserId);
        PromptTestSetRun runB = requireOwnedRun(request.getRunIdB(), currentUserId);
        if (!Objects.equals(runA.getSetId(), runB.getSetId())) {
            throw new BusinessException("只能对比同一个用例集的两次运行");
        }

        Map<Long, PromptTestCaseResult> resultsA = loadResultsByCase(request.getRunIdA());
        Map<Long, PromptTestCaseResult> resultsB = loadResultsByCase(request.getRunIdB());

        List<Long> caseIds = new ArrayList<>(resultsA.keySet());
        for (Long id : resultsB.keySet()) {
            if (!resultsA.containsKey(id)) caseIds.add(id);
        }

        List<PromptTestCaseComparison> comparisons = new ArrayList<>(caseIds.size());
        for (Long caseId : caseIds) {
            PromptTestCaseResult a = resultsA.get(caseId);
            PromptTestCaseResult b = resultsB.get(caseId);
            Boolean identical = null;
            if (a != null && b != null && a.isSuccess() && b.isSuccess()) {
                identical = Objects.equals(trimContent(a.getContent()), trimContent(b.getContent()));
            }
            comparisons.add(PromptTestCaseComparison.builder()
                    .caseId(caseId)
                    .question(a != null ? a.getQuestion() : b.getQuestion())
                    .resultA(a)
                    .resultB(b)
                    .answerIdentical(identical)
                    .build());
        }
        comparisons.sort((x, y) -> Long.compare(x.getCaseId(), y.getCaseId()));

        return PromptTestSetCompareResponse.builder()
                .runA(toRunDTO(runA))
                .runB(toRunDTO(runB))
                .comparisons(comparisons)
                .comparedCases(comparisons.size())
                .build();
    }

    private Map<Long, PromptTestCaseResult> loadResultsByCase(Long runId) {
        PromptTestSetRun run = runMapper.selectById(runId);
        LambdaQueryWrapper<PromptTestCaseResultEntity> query = new LambdaQueryWrapper<PromptTestCaseResultEntity>()
                .eq(PromptTestCaseResultEntity::getRunId, runId);
        if (run != null && run.getExecutionToken() != null) {
            query.eq(PromptTestCaseResultEntity::getExecutionToken, run.getExecutionToken());
        }
        return caseResultMapper.selectList(query)
                .stream().map(this::toCaseResultDTO)
                .collect(Collectors.toMap(PromptTestCaseResult::getCaseId, Function.identity()));
    }

    private String trimContent(String content) {
        return content == null ? "" : content.trim();
    }

    // ── Private helpers ───────────────────────────────────────────────

    private List<PromptTestCase> listCases(Long setId) {
        return testCaseMapper.selectList(new LambdaQueryWrapper<PromptTestCase>()
                .eq(PromptTestCase::getSetId, setId)
                .orderByAsc(PromptTestCase::getSortOrder)
                .orderByAsc(PromptTestCase::getId));
    }

    private int nextSortOrder(Long setId) {
        List<PromptTestCase> cases = listCases(setId);
        return cases.isEmpty() ? 0 : (cases.get(cases.size() - 1).getSortOrder() != null
                ? cases.get(cases.size() - 1).getSortOrder() + 1 : cases.size());
    }

    private PromptTestSet requireOwned(Long id, Long userId) {
        PromptTestSet set = testSetMapper.selectById(id);
        if (set == null) throw new BusinessException("测试用例集不存在或已删除");
        if (!set.getUserId().equals(userId)) throw new BusinessException("无权操作该测试用例集");
        return set;
    }

    private PromptTestSetRun requireOwnedRun(Long runId, Long userId) {
        PromptTestSetRun run = runMapper.selectById(runId);
        if (run == null) throw new BusinessException("运行记录不存在");
        if (!run.getUserId().equals(userId)) throw new BusinessException("无权查看该运行记录");
        return run;
    }

    private PromptTestSetRunDTO toRunDTO(PromptTestSetRun run) {
        return PromptTestSetRunDTO.builder()
                .id(run.getId())
                .templateId(run.getTemplateId())
                .templateVersion(run.getTemplateVersion())
                .templateName(run.getTemplateName())
                .templateContent(run.getTemplateContent())
                .knowledgeBaseId(run.getKnowledgeBaseId())
                .totalCases(run.getTotalCases())
                .successCount(run.getSuccessCount())
                .failureCount(run.getFailureCount())
                .passCount(run.getPassCount())
                .passRate(computePassRate(run.getPassCount(), run.getTotalCases()))
                .totalElapsedMs(run.getTotalElapsedMs())
                .status(run.getStatus())
                .attemptNumber(run.getAttemptNumber())
                .progressCount(run.getProgressCount())
                .errorMessage(run.getErrorMessage())
                .startedAt(run.getStartedAt())
                .completedAt(run.getCompletedAt())
                .createdAt(run.getCreatedAt())
                .build();
    }

    private PromptTestSetRunStatusDTO toStatusDTO(PromptTestSetRun run) {
        return PromptTestSetRunStatusDTO.builder()
                .id(run.getId())
                .setId(run.getSetId())
                .status(run.getStatus())
                .attemptNumber(run.getAttemptNumber())
                .progressCount(run.getProgressCount())
                .totalCases(run.getTotalCases())
                .successCount(run.getSuccessCount())
                .failureCount(run.getFailureCount())
                .passCount(run.getPassCount())
                .passRate(computePassRate(run.getPassCount(), run.getTotalCases()))
                .errorMessage(run.getErrorMessage())
                .scheduledAt(run.getScheduledAt())
                .startedAt(run.getStartedAt())
                .completedAt(run.getCompletedAt())
                .createdAt(run.getCreatedAt())
                .build();
    }

    private PromptTestCaseResult toCaseResultDTO(PromptTestCaseResultEntity entity) {
        return PromptTestCaseResult.builder()
                .caseId(entity.getCaseId())
                .question(entity.getQuestion())
                .renderedTemplate(entity.getRenderedTemplate())
                .content(entity.getContent())
                .model(entity.getModel())
                .tokenCount(entity.getTokenCount())
                .tokenUsage(entity.getTokenUsage())
                .sources(entity.getSources())
                .elapsedMs(entity.getElapsedMs())
                .success(entity.isSuccess())
                .passed(entity.isPassed())
                .passNotes(entity.getPassNotes())
                .error(entity.getError())
                .build();
    }

    private PromptTestCase requireCaseInSet(Long caseId, Long setId) {
        PromptTestCase tc = testCaseMapper.selectById(caseId);
        if (tc == null || !tc.getSetId().equals(setId)) {
            throw new BusinessException("测试用例不存在或不属于该用例集");
        }
        return tc;
    }

    private void ensureNameAvailable(String rawName, Long userId, Long ignoredId) {
        String name = rawName == null ? "" : rawName.trim();
        LambdaQueryWrapper<PromptTestSet> query = new LambdaQueryWrapper<PromptTestSet>()
                .eq(PromptTestSet::getUserId, userId)
                .eq(PromptTestSet::getName, name);
        if (ignoredId != null) query.ne(PromptTestSet::getId, ignoredId);
        if (testSetMapper.selectCount(query) > 0) {
            throw new BusinessException("已经存在同名测试用例集");
        }
    }

    private String clean(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private Map<String, Object> emptyToNull(Map<String, Object> variables) {
        return variables == null || variables.isEmpty() ? null : variables;
    }

    private <T> List<T> emptyToNullList(List<T> values) {
        return values == null || values.isEmpty() ? null : values;
    }

    private PromptTestSetDTO toSetDTO(PromptTestSet set) {
        long count = testCaseMapper.selectCount(new LambdaQueryWrapper<PromptTestCase>()
                .eq(PromptTestCase::getSetId, set.getId()));
        return PromptTestSetDTO.builder()
                .id(set.getId())
                .name(set.getName())
                .description(set.getDescription())
                .caseCount(count)
                .createdAt(set.getCreatedAt())
                .updatedAt(set.getUpdatedAt())
                .build();
    }

    private PromptTestSetDetailDTO toDetail(PromptTestSet set, List<PromptTestCase> cases) {
        return PromptTestSetDetailDTO.builder()
                .id(set.getId())
                .name(set.getName())
                .description(set.getDescription())
                .createdAt(set.getCreatedAt())
                .updatedAt(set.getUpdatedAt())
                .cases(cases.stream().map(this::toCaseDTO).toList())
                .build();
    }

    private PromptTestCaseDTO toCaseDTO(PromptTestCase tc) {
        return PromptTestCaseDTO.builder()
                .id(tc.getId())
                .question(tc.getQuestion())
                .variables(tc.getVariables())
                .expectedKeywords(tc.getExpectedKeywords())
                .requiredDocumentIds(tc.getRequiredDocumentIds())
                .sortOrder(tc.getSortOrder())
                .build();
    }
}
