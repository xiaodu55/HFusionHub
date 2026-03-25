package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseResult;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.PromptTestCase;
import com.hfusionhub.entity.PromptTestSet;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.PromptTestCaseMapper;
import com.hfusionhub.mapper.PromptTestSetMapper;
import com.hfusionhub.service.PromptTestSetService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 提示词测试用例集服务实现。 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PromptTestSetServiceImpl implements PromptTestSetService {

    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{\\s*([\\p{L}\\p{N}_.]+)\\s*}}");

    private final PromptTestSetMapper testSetMapper;
    private final PromptTestCaseMapper testCaseMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final AiClient aiClient;

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

        long start = System.currentTimeMillis();
        int success = 0;
        List<PromptTestCaseResult> results = new ArrayList<>(cases.size());

        for (PromptTestCase tc : cases) {
            PromptTestCaseResult r = runSingle(set, tc, request, currentUserId);
            if (r.isSuccess()) success++;
            results.add(r);
        }

        return PromptTestSetRunResponse.builder()
                .setId(set.getId())
                .totalCases(cases.size())
                .successCount(success)
                .failureCount(cases.size() - success)
                .totalElapsedMs(System.currentTimeMillis() - start)
                .results(results)
                .build();
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
