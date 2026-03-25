package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/** 提示词测试用例集服务实现。 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PromptTestSetServiceImpl implements PromptTestSetService {

    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{\\s*([\\p{L}\\p{N}_.]+)\\s*}}");

    private final PromptTestSetMapper testSetMapper;
    private final PromptTestCaseMapper testCaseMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final PromptTemplateMapper promptTemplateMapper;
    private final AiClient aiClient;
    private final PromptTestSetRunMapper runMapper;
    private final PromptTestCaseResultMapper caseResultMapper;

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

    @Override
    public PromptTestSetRunResponse run(Long setId, PromptTestSetRunRequest request) {
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

        long start = System.currentTimeMillis();
        int success = 0;
        List<PromptTestCaseResult> results = new ArrayList<>(cases.size());

        for (PromptTestCase tc : cases) {
            PromptTestCaseResult r = runSingle(set, tc, resolved, currentUserId);
            if (r.isSuccess()) success++;
            results.add(r);
        }

        long totalElapsed = System.currentTimeMillis() - start;

        // Persist run history (run + per-case results) for version comparison.
        Long runId = persistRun(set, currentUserId, resolved, results, success, totalElapsed);

        return PromptTestSetRunResponse.builder()
                .setId(set.getId())
                .runId(runId)
                .templateId(resolved.getTemplateId())
                .templateVersion(resolved.getTemplateVersion())
                .templateName(resolved.getTemplateName())
                .totalCases(cases.size())
                .successCount(success)
                .failureCount(cases.size() - success)
                .totalElapsedMs(totalElapsed)
                .results(results)
                .build();
    }

    /**
     * 绑定模板时按当前用户校验并从数据库读取真实模板名称、版本与内容快照；
     * 未绑定（自定义模板）时清除模板关联，历史标记为自定义模板。
     */
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

    protected Long persistRun(PromptTestSet set, Long userId, PromptTestSetRunRequest request,
                              List<PromptTestCaseResult> results, int success, long totalElapsed) {
        PromptTestSetRun run = new PromptTestSetRun();
        run.setSetId(set.getId());
        run.setUserId(userId);
        run.setTemplateId(request.getTemplateId());
        run.setTemplateVersion(request.getTemplateVersion());
        run.setTemplateName(clean(request.getTemplateName()));
        run.setTemplateContent(request.getTemplateContent());
        run.setKnowledgeBaseId(request.getKnowledgeBaseId());
        run.setTotalCases(results.size());
        run.setSuccessCount(success);
        run.setFailureCount(results.size() - success);
        run.setTotalElapsedMs(totalElapsed);
        runMapper.insert(run);

        for (PromptTestCaseResult r : results) {
            PromptTestCaseResultEntity entity = new PromptTestCaseResultEntity();
            entity.setRunId(run.getId());
            entity.setCaseId(r.getCaseId());
            entity.setQuestion(r.getQuestion());
            entity.setRenderedTemplate(r.getRenderedTemplate());
            entity.setContent(r.getContent());
            entity.setModel(r.getModel());
            entity.setTokenCount(r.getTokenCount());
            entity.setTokenUsage(r.getTokenUsage());
            entity.setSources(r.getSources());
            entity.setElapsedMs(r.getElapsedMs());
            entity.setSuccess(r.isSuccess());
            entity.setError(r.getError());
            caseResultMapper.insert(entity);
        }
        return run.getId();
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
            return PromptTestCaseResult.builder()
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
        } catch (Exception e) {
            log.warn("批量运行单个用例失败: setId={}, caseId={}: {}", set.getId(), tc.getId(), e.getMessage());
            return PromptTestCaseResult.builder()
                    .caseId(tc.getId())
                    .question(tc.getQuestion())
                    .renderedTemplate(rendered)
                    .elapsedMs(System.currentTimeMillis() - caseStart)
                    .success(false)
                    .error(e.getMessage())
                    .build();
        }
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
        List<PromptTestCaseResultEntity> entities = caseResultMapper.selectList(
                new LambdaQueryWrapper<PromptTestCaseResultEntity>()
                        .eq(PromptTestCaseResultEntity::getRunId, runId)
                        .orderByAsc(PromptTestCaseResultEntity::getId));
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
        return caseResultMapper.selectList(
                        new LambdaQueryWrapper<PromptTestCaseResultEntity>()
                                .eq(PromptTestCaseResultEntity::getRunId, runId))
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
                .totalElapsedMs(run.getTotalElapsedMs())
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
                .sortOrder(tc.getSortOrder())
                .build();
    }
}
