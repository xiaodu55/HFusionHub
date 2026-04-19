package com.hfusionhub.service.impl;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.PromptTestSetRunStatus;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.PromptTestCaseComparison;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetCompareRequest;
import com.hfusionhub.dto.PromptTestSetCompareResponse;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetRunStatusDTO;
import com.hfusionhub.dto.PromptTestCaseResult;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.PromptTestCase;
import com.hfusionhub.entity.PromptTestSet;
import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.PromptTestCaseMapper;
import com.hfusionhub.mapper.PromptTestCaseResultMapper;
import com.hfusionhub.mapper.PromptTestSetMapper;
import com.hfusionhub.mapper.PromptTestSetRunMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link PromptTestSetServiceImpl} — prompt test case sets.
 *
 * <p>Verifies:
 * <ul>
 *   <li>Ownership validation on set and case operations.</li>
 *   <li>Batch run: each question executed via AiClient, single-case failure does
 *       not abort the whole run, {{var}} substitution applied.</li>
 *   <li>KB ownership checked before batch run.</li>
 *   <li>Empty set rejected.</li>
 * </ul>
 */
class PromptTestSetServiceImplTest {

    private PromptTestSetMapper testSetMapper;
    private PromptTestCaseMapper testCaseMapper;
    private KnowledgeBaseMapper knowledgeBaseMapper;
    private com.hfusionhub.mapper.PromptTemplateMapper promptTemplateMapper;
    private AiClient aiClient;
    private PromptTestSetRunMapper runMapper;
    private PromptTestCaseResultMapper caseResultMapper;
    private PromptTestSetServiceImpl service;

    /** The most recently inserted run row (mocked persistence). */
    private final AtomicReference<PromptTestSetRun> insertedRun = new AtomicReference<>();

    @BeforeEach
    void setUp() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        // 纯 Mockito 环境无 Spring 容器，需手动初始化 LambdaWrapper 的实体缓存
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(
                new org.apache.ibatis.builder.MapperBuilderAssistant(
                        new com.baomidou.mybatisplus.core.MybatisConfiguration(), ""),
                com.hfusionhub.entity.PromptTestSetRun.class);
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(
                new org.apache.ibatis.builder.MapperBuilderAssistant(
                        new com.baomidou.mybatisplus.core.MybatisConfiguration(), ""),
                com.hfusionhub.entity.PromptTestCaseResultEntity.class);
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(
                new org.apache.ibatis.builder.MapperBuilderAssistant(
                        new com.baomidou.mybatisplus.core.MybatisConfiguration(), ""),
                com.hfusionhub.entity.PromptTestSet.class);
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(
                new org.apache.ibatis.builder.MapperBuilderAssistant(
                        new com.baomidou.mybatisplus.core.MybatisConfiguration(), ""),
                com.hfusionhub.entity.PromptTestCase.class);

        testSetMapper = mock(PromptTestSetMapper.class);
        testCaseMapper = mock(PromptTestCaseMapper.class);
        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        promptTemplateMapper = mock(com.hfusionhub.mapper.PromptTemplateMapper.class);
        aiClient = mock(AiClient.class);
        runMapper = mock(PromptTestSetRunMapper.class);
        caseResultMapper = mock(PromptTestCaseResultMapper.class);
        service = new PromptTestSetServiceImpl(
                testSetMapper, testCaseMapper, knowledgeBaseMapper, promptTemplateMapper, aiClient,
                runMapper, caseResultMapper, new PromptTestSetCaseWriter(runMapper, caseResultMapper),
                2, 0);

        // Simulate DB identity assignment + read-back for the async execute path.
        insertedRun.set(null);
        when(runMapper.insert(any())).thenAnswer(inv -> {
            PromptTestSetRun r = inv.getArgument(0);
            if (r.getId() == null) r.setId(1L);
            insertedRun.set(r);
            return 1;
        });
        when(runMapper.selectById(1L)).thenAnswer(inv -> insertedRun.get());
        when(runMapper.selectById(anyLong())).thenAnswer(inv -> insertedRun.get());
        when(runMapper.update(any(), any())).thenReturn(1);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    private PromptTestSet ownedSet() {
        PromptTestSet set = new PromptTestSet();
        set.setId(10L);
        set.setUserId(1L);
        set.setName("回归集");
        return set;
    }

    private PromptTestCase caseOf(Long id, String question, Map<String, Object> vars) {
        PromptTestCase tc = new PromptTestCase();
        tc.setId(id);
        tc.setSetId(10L);
        tc.setQuestion(question);
        tc.setVariables(vars);
        tc.setSortOrder(0);
        return tc;
    }

    // ── Ownership ─────────────────────────────────────────────────────

    @Test
    void rejectsSetNotOwnedByCurrentUser() {
        StpUtil.login(1L);
        PromptTestSet set = ownedSet();
        set.setUserId(2L);
        when(testSetMapper.selectById(10L)).thenReturn(set);

        PromptTestSetSaveDTO dto = new PromptTestSetSaveDTO();
        dto.setName("x");
        assertThrows(BusinessException.class, () -> service.getDetail(10L));
    }

    @Test
    void rejectsCaseNotInSet() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase foreign = caseOf(99L, "q", null);
        foreign.setSetId(20L);
        when(testCaseMapper.selectById(99L)).thenReturn(foreign);

        PromptTestCaseSaveDTO dto = new PromptTestCaseSaveDTO();
        dto.setQuestion("q");
        assertThrows(BusinessException.class, () -> service.updateCase(10L, 99L, dto));
    }

    @Test
    void rejectsDuplicateSetName() {
        StpUtil.login(1L);
        when(testSetMapper.selectCount(any())).thenReturn(1L);

        PromptTestSetSaveDTO dto = new PromptTestSetSaveDTO();
        dto.setName("重复");
        assertThrows(BusinessException.class, () -> service.create(dto));
    }

    // ── Batch run ─────────────────────────────────────────────────────

    @Test
    void rejectsEmptySetRun() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of());

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        assertThrows(BusinessException.class, () -> service.run(10L, request));
    }

    @Test
    void rejectsForeignKnowledgeBase() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "q", null)));

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(7L);
        kb.setUserId(2L);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(kb);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        request.setKnowledgeBaseId(7L);
        assertThrows(BusinessException.class, () -> service.run(10L, request));
    }

    @Test
    void runsAllCasesAndSubstitutesVariables() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());

        Map<String, Object> vars = new HashMap<>();
        vars.put("role", "客服");
        vars.put("topic", "退款");
        when(testCaseMapper.selectList(any())).thenReturn(List.of(
                caseOf(1L, "如何退款？", vars),
                caseOf(2L, "多久到账？", null)
        ));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(100);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是{{role}}，关于{{topic}}请回答");
        PromptTestSetRunResponse response = runAndExecute(10L, request);

        assertEquals(2, response.getTotalCases());
        assertEquals(2, response.getSuccessCount());
        assertEquals(0, response.getFailureCount());
        assertEquals(2, response.getResults().size());

        // Variable substitution applied for case 1
        assertEquals("你是客服，关于退款请回答", response.getResults().get(0).getRenderedTemplate());
        // Case 2 has no variables → template unchanged
        assertEquals("你是{{role}}，关于{{topic}}请回答", response.getResults().get(1).getRenderedTemplate());
    }

    @Test
    void substitutesChineseVariableNames() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());

        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        vars.put("主题", "退款");
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", vars)));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是{{角色}}，关于{{主题}}请回答");
        PromptTestSetRunResponse response = runAndExecute(10L, request);

        assertEquals(1, response.getSuccessCount());
        assertEquals("你是客服，关于退款请回答", response.getResults().get(0).getRenderedTemplate());
    }

    @Test
    void singleCaseFailureDoesNotAbortRun() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(
                caseOf(1L, "ok", null),
                caseOf(2L, "boom", null)
        ));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        resp.setModel("deepseek-v4-flash");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong()))
                .thenReturn(resp)
                .thenThrow(new RuntimeException("boom"));

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        PromptTestSetRunResponse response = runAndExecute(10L, request);

        assertEquals(2, response.getTotalCases());
        assertEquals(1, response.getSuccessCount());
        assertEquals(1, response.getFailureCount());
        assertTrue(response.getResults().get(0).isSuccess());
        assertFalse(response.getResults().get(1).isSuccess());
        assertNotNull(response.getResults().get(1).getError());
    }

    @Test
    void kbBoundRunUsesAgentV1Chat() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "q", null)));

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(7L);
        kb.setUserId(1L);
        when(knowledgeBaseMapper.selectById(7L)).thenReturn(kb);

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.agentV1Chat(anyString(), isNull(), anyLong(), any(), anyString(),
                anyString(), anyInt(), isNull(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        request.setKnowledgeBaseId(7L);
        PromptTestSetRunResponse response = runAndExecute(10L, request);

        assertEquals(1, response.getSuccessCount());
        verify(aiClient).agentV1Chat(eq("q"), isNull(), eq(7L), any(), eq("模板"),
                eq("detailed"), eq(5), isNull(), eq(1L));
    }

    // ── Case CRUD ─────────────────────────────────────────────────────

    @Test
    void addCaseStoresQuestionAndVariables() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of());

        PromptTestCaseSaveDTO dto = new PromptTestCaseSaveDTO();
        dto.setQuestion("问题");
        Map<String, Object> vars = new HashMap<>();
        vars.put("role", "客服");
        dto.setVariables(vars);

        PromptTestCaseDTO result = service.addCase(10L, dto);

        assertNotNull(result);
        assertEquals("问题", result.getQuestion());
        assertEquals("客服", result.getVariables().get("role"));
    }

    @Test
    void deleteSetCascadesCases() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());

        service.delete(10L);

        verify(testCaseMapper).delete(any());
        verify(testSetMapper).deleteById(10L);
    }

    // ── Run history & comparison ──────────────────────────────────────

    @Test
    void listRunsRejectsForeignSet() {
        StpUtil.login(1L);
        PromptTestSet set = ownedSet();
        set.setUserId(2L);
        when(testSetMapper.selectById(10L)).thenReturn(set);
        assertThrows(BusinessException.class, () -> service.listRuns(10L));
    }

    @Test
    void runDetailRejectsForeignRun() {
        StpUtil.login(1L);
        com.hfusionhub.entity.PromptTestSetRun run = new com.hfusionhub.entity.PromptTestSetRun();
        run.setId(99L);
        run.setUserId(2L);
        when(runMapper.selectById(99L)).thenReturn(run);
        assertThrows(BusinessException.class, () -> service.getRunDetail(99L));
    }

    @Test
    void compareRejectsRunsFromDifferentSets() {
        StpUtil.login(1L);
        com.hfusionhub.entity.PromptTestSetRun a = new com.hfusionhub.entity.PromptTestSetRun();
        a.setId(1L); a.setUserId(1L); a.setSetId(10L);
        com.hfusionhub.entity.PromptTestSetRun b = new com.hfusionhub.entity.PromptTestSetRun();
        b.setId(2L); b.setUserId(1L); b.setSetId(20L);
        when(runMapper.selectById(1L)).thenReturn(a);
        when(runMapper.selectById(2L)).thenReturn(b);

        PromptTestSetCompareRequest request = new PromptTestSetCompareRequest();
        request.setRunIdA(1L);
        request.setRunIdB(2L);
        assertThrows(BusinessException.class, () -> service.compare(request));
    }

    @Test
    void compareBuildsPerCaseRowsAndFlagsIdenticalAnswers() {
        StpUtil.login(1L);
        com.hfusionhub.entity.PromptTestSetRun a = new com.hfusionhub.entity.PromptTestSetRun();
        a.setId(1L); a.setUserId(1L); a.setSetId(10L);
        a.setTemplateVersion(1);
        com.hfusionhub.entity.PromptTestSetRun b = new com.hfusionhub.entity.PromptTestSetRun();
        b.setId(2L); b.setUserId(1L); b.setSetId(10L);
        b.setTemplateVersion(2);
        when(runMapper.selectById(1L)).thenReturn(a);
        when(runMapper.selectById(2L)).thenReturn(b);

        when(caseResultMapper.selectList(any())).thenReturn(List.of(
                caseResult(1L, 1L, "问题A", "回答一", 100, 1200, true),
                caseResult(2L, 1L, "问题B", "失败A", 50, 800, false)
        ));

        PromptTestSetCompareRequest request = new PromptTestSetCompareRequest();
        request.setRunIdA(1L);
        request.setRunIdB(2L);
        PromptTestSetCompareResponse response = service.compare(request);

        assertEquals(2, response.getComparedCases());
        assertEquals(2, response.getComparisons().size());
        assertEquals(1, response.getRunA().getTemplateVersion());
        assertEquals(2, response.getRunB().getTemplateVersion());

        // Case 1: same answer → identical=true
        PromptTestCaseComparison c1 = response.getComparisons().get(0);
        assertEquals(Boolean.TRUE, c1.getAnswerIdentical());
        // Case 2: both failed → identical=null
        assertEquals(null, response.getComparisons().get(1).getAnswerIdentical());
    }

    @Test
    void runPersistsHistory() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        Map<String, Object> vars = new HashMap<>();
        vars.put("role", "客服");
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", vars)));

        com.hfusionhub.entity.PromptTemplate template = new com.hfusionhub.entity.PromptTemplate();
        template.setId(5L);
        template.setUserId(1L);
        template.setName("客服助手");
        template.setVersion(3);
        template.setContent("你是{{role}}");
        when(promptTemplateMapper.selectById(5L)).thenReturn(template);

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是{{role}}");
        request.setTemplateId(5L);
        request.setTemplateVersion(99);
        request.setTemplateName("伪造名称");

        PromptTestSetRunResponse response = runAndExecute(10L, request);

        // Insert happens at submit time with the resolved DB snapshot (counts filled later).
        // Async submit status is verified separately (runQueuesPendingRunAndReturnsStatus).
        verify(runMapper).insert(argThat(r ->
                r.getTemplateId().equals(5L) && r.getTemplateVersion().equals(3)
                        && "客服助手".equals(r.getTemplateName())
                        && r.getTotalCases() == 1 && r.getSetId().equals(10L)));
        verify(caseResultMapper).insert(argThat(e ->
                e.getCaseId().equals(1L) && "你是客服".equals(e.getRenderedTemplate())));
        assertEquals(5L, response.getTemplateId());
        assertEquals(3, response.getTemplateVersion());
        assertEquals("客服助手", response.getTemplateName());
    }

    @Test
    void runRejectsForgedForeignTemplate() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));

        com.hfusionhub.entity.PromptTemplate foreign = new com.hfusionhub.entity.PromptTemplate();
        foreign.setId(5L);
        foreign.setUserId(2L);
        when(promptTemplateMapper.selectById(5L)).thenReturn(foreign);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        request.setTemplateId(5L);
        assertThrows(BusinessException.class, () -> service.run(10L, request));
        verify(runMapper, never()).insert(any());
    }

    @Test
    void runRejectsMissingTemplate() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));
        when(promptTemplateMapper.selectById(5L)).thenReturn(null);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        request.setTemplateId(5L);
        assertThrows(BusinessException.class, () -> service.run(10L, request));
        verify(runMapper, never()).insert(any());
    }

    @Test
    void runWithBoundTemplateIgnoresEditedContentAndUsesRealSnapshot() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        Map<String, Object> vars = new HashMap<>();
        vars.put("role", "客服");
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", vars)));

        com.hfusionhub.entity.PromptTemplate template = new com.hfusionhub.entity.PromptTemplate();
        template.setId(5L);
        template.setUserId(1L);
        template.setName("客服助手");
        template.setVersion(3);
        template.setContent("你是{{role}}，来自模板");
        when(promptTemplateMapper.selectById(5L)).thenReturn(template);

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        // Client-sent content differs from the real template snapshot (user edited it)
        request.setTemplateContent("被篡改的自定义内容");
        request.setTemplateId(5L);

        PromptTestSetRunResponse response = runAndExecute(10L, request);

        // Execution + persisted content must come from the DB snapshot, not the edited payload
        verify(aiClient).chat(eq("如何退款？"), isNull(), isNull(), any(), eq("你是客服，来自模板"), anyLong());
        verify(caseResultMapper).insert(argThat(e ->
                "你是客服，来自模板".equals(e.getRenderedTemplate())));
        verify(runMapper).insert(argThat(r ->
                r.getTemplateId().equals(5L) && "客服助手".equals(r.getTemplateName())
                        && "你是{{role}}，来自模板".equals(r.getTemplateContent())));
        assertEquals("客服助手", response.getTemplateName());
    }

    @Test
    void runWithoutTemplateClearsAssociation() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("自定义模板");
        request.setTemplateVersion(3);
        request.setTemplateName("伪造名称");

        PromptTestSetRunResponse response = runAndExecute(10L, request);

        verify(runMapper).insert(argThat(r ->
                r.getTemplateId() == null && r.getTemplateVersion() == null
                        && r.getTemplateName() == null
                        && "自定义模板".equals(r.getTemplateContent())));
        assertNull(response.getTemplateId());
        assertNull(response.getTemplateName());
    }

    @Test
    void runWithBlankContentRejected() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("  ");
        assertThrows(BusinessException.class, () -> service.run(10L, request));
    }

    // ── Pass rules ────────────────────────────────────────────────────

    @Test
    void passesWhenAnswerContainsAllExpectedKeywords() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase tc = caseOf(1L, "如何退款？", null);
        tc.setExpectedKeywords(List.of("退款", "7天"));
        when(testCaseMapper.selectList(any())).thenReturn(List.of(tc));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("亲，您可以在7天内申请退款。");
        resp.setModel("deepseek-v4-flash");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        PromptTestCaseResult r = response.getResults().get(0);
        assertTrue(r.isSuccess());
        assertTrue(r.isPassed());
        assertNull(r.getPassNotes());
        assertEquals(1, response.getPassCount());
        assertEquals(100.0, response.getPassRate());
    }

    @Test
    void failsWhenKeywordMissingCaseInsensitive() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase tc = caseOf(1L, "如何退款？", null);
        tc.setExpectedKeywords(List.of("REFUND", "客服"));
        when(testCaseMapper.selectList(any())).thenReturn(List.of(tc));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("请致电400热线（不支持refund操作）。");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        PromptTestCaseResult r = response.getResults().get(0);
        assertTrue(r.isSuccess());
        assertFalse(r.isPassed());
        assertNotNull(r.getPassNotes());
        assertTrue(r.getPassNotes().stream().anyMatch(n -> n.contains("客服")));
        assertEquals(0, response.getPassCount());
        assertEquals(0.0, response.getPassRate());
    }

    @Test
    void passesWhenAllRequiredDocumentsCited() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase tc = caseOf(1L, "退款政策？", null);
        tc.setRequiredDocumentIds(List.of(11L, 22L));
        when(testCaseMapper.selectList(any())).thenReturn(List.of(tc));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("根据政策文档……");
        resp.setSources(List.of(
                Map.of("document_id", 11L, "chunk_id", "c1"),
                Map.of("document_id", 22L, "chunk_id", "c2")
        ));
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        assertTrue(response.getResults().get(0).isPassed());
        assertEquals(1, response.getPassCount());
    }

    @Test
    void failsWhenRequiredDocumentNotCited() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase tc = caseOf(1L, "退款政策？", null);
        tc.setRequiredDocumentIds(List.of(11L, 33L));
        when(testCaseMapper.selectList(any())).thenReturn(List.of(tc));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("根据政策文档……");
        resp.setSources(List.of(Map.of("document_id", 11L, "chunk_id", "c1")));
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        PromptTestCaseResult r = response.getResults().get(0);
        assertTrue(r.isSuccess());
        assertFalse(r.isPassed());
        assertTrue(r.getPassNotes().stream().anyMatch(n -> n.contains("33")));
        assertEquals(0, response.getPassCount());
    }

    @Test
    void noRulesMeansPassedEqualsSuccess() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("请致电400。");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        assertTrue(response.getResults().get(0).isPassed());
        assertEquals(1, response.getPassCount());
        assertEquals(100.0, response.getPassRate());
    }

    @Test
    void failedCaseIsNeverPassed() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        PromptTestCase tc = caseOf(1L, "如何退款？", null);
        tc.setExpectedKeywords(List.of("退款"));
        when(testCaseMapper.selectList(any())).thenReturn(List.of(tc));

        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong()))
                .thenThrow(new RuntimeException("boom"));

        PromptTestSetRunResponse response = runAndExecute(10L, request("模板"));

        PromptTestCaseResult r = response.getResults().get(0);
        assertFalse(r.isSuccess());
        assertFalse(r.isPassed());
        assertEquals(0, response.getPassCount());
        assertEquals(0.0, response.getPassRate());
    }

    // ── Async lifecycle (queue / progress / cancel / retry) ───────────

    @Test
    void runQueuesPendingRunAndReturnsStatus() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(
                caseOf(1L, "如何退款？", null),
                caseOf(2L, "多久到账？", null)
        ));

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        PromptTestSetRunStatusDTO status = service.run(10L, request);

        assertNotNull(status.getId());
        assertEquals(PromptTestSetRunStatus.PENDING, status.getStatus());
        assertEquals(2, status.getTotalCases());
        assertEquals(0, status.getProgressCount());
        assertEquals(1, status.getAttemptNumber());
        verify(runMapper).insert(argThat(r ->
                PromptTestSetRunStatus.PENDING.equals(r.getStatus())
                        && r.getTotalCases() == 2 && r.getSetId().equals(10L)));
        verify(aiClient, never()).chat(anyString(), any(), any(), any(), anyString(), anyLong());
    }

    @Test
    void executeRunMarksSucceededAndAdvancesProgress() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(
                caseOf(1L, "q1", null),
                caseOf(2L, "q2", null)
        ));
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunStatusDTO queued = service.run(10L, request("模板"));
        PromptTestSetRunResponse response = service.executeRun(queued.getId());

        assertEquals(PromptTestSetRunStatus.SUCCEEDED, insertedRun.get().getStatus());
        assertEquals(2, insertedRun.get().getProgressCount());
        assertEquals(2, response.getSuccessCount());
        assertEquals(2, response.getResults().size());
        verify(caseResultMapper, times(2)).insert(any());
    }

    @Test
    void singleCaseRetriesOnTransientFailure() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "q1", null)));
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        // First attempt fails transiently, retry succeeds
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong()))
                .thenThrow(new RuntimeException("boom"))
                .thenReturn(resp);

        PromptTestSetRunStatusDTO queued = service.run(10L, request("模板"));
        PromptTestSetRunResponse response = service.executeRun(queued.getId());

        assertEquals(1, response.getSuccessCount());
        assertTrue(response.getResults().get(0).isSuccess());
        verify(aiClient, times(2)).chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong());
    }

    @Test
    void cancelPendingRunPreventsExecution() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));

        PromptTestSetRunStatusDTO queued = service.run(10L, request("模板"));
        PromptTestSetRunStatusDTO cancelled = service.cancelRun(queued.getId());

        assertEquals(PromptTestSetRunStatus.CANCELLED, cancelled.getStatus());
        // Worker skips already-terminal runs
        assertNull(service.executeRun(queued.getId()));
        verify(caseResultMapper, never()).insert(any());
        verify(aiClient, never()).chat(anyString(), any(), any(), any(), anyString(), anyLong());
    }

    @Test
    void cancelTerminalRunIsNoOp() {
        StpUtil.login(1L);
        when(testSetMapper.selectById(10L)).thenReturn(ownedSet());
        when(testCaseMapper.selectList(any())).thenReturn(List.of(caseOf(1L, "如何退款？", null)));
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString(), anyLong())).thenReturn(resp);

        PromptTestSetRunStatusDTO queued = service.run(10L, request("模板"));
        service.executeRun(queued.getId());

        PromptTestSetRunStatusDTO cancelled = service.cancelRun(queued.getId());
        assertEquals(PromptTestSetRunStatus.SUCCEEDED, cancelled.getStatus());
    }

    @Test
    void retryFailedRunRequeuesWithNextAttempt() {
        StpUtil.login(1L);
        PromptTestSetRun failed = new PromptTestSetRun();
        failed.setId(7L);
        failed.setUserId(1L);
        failed.setSetId(10L);
        failed.setStatus(PromptTestSetRunStatus.FAILED);
        failed.setAttemptNumber(1);
        PromptTestSetRun requeued = new PromptTestSetRun();
        requeued.setId(7L);
        requeued.setUserId(1L);
        requeued.setSetId(10L);
        requeued.setStatus(PromptTestSetRunStatus.PENDING);
        requeued.setAttemptNumber(2);
        when(runMapper.selectById(7L)).thenReturn(failed, requeued);

        PromptTestSetRunStatusDTO status = service.retryRun(7L);

        assertEquals(PromptTestSetRunStatus.PENDING, status.getStatus());
        assertEquals(2, status.getAttemptNumber());
        verify(caseResultMapper).delete(any());
        verify(runMapper).update(isNull(), any());
    }

    @Test
    void retrySucceededRunIsRejected() {
        StpUtil.login(1L);
        PromptTestSetRun done = new PromptTestSetRun();
        done.setId(8L);
        done.setUserId(1L);
        done.setSetId(10L);
        done.setStatus(PromptTestSetRunStatus.SUCCEEDED);
        done.setAttemptNumber(1);
        when(runMapper.selectById(8L)).thenReturn(done);

        assertThrows(BusinessException.class, () -> service.retryRun(8L));
        verify(caseResultMapper, never()).delete(any());
    }

    private PromptTestSetRunRequest request(String content) {
        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent(content);
        return request;
    }

    /** Submit then synchronously execute (mirrors the worker path in tests with queue disabled). */
    private PromptTestSetRunResponse runAndExecute(Long setId, PromptTestSetRunRequest request) {
        PromptTestSetRunStatusDTO status = service.run(setId, request);
        return service.executeRun(status.getId());
    }

    private com.hfusionhub.entity.PromptTestCaseResultEntity caseResult(
            Long caseId, Long runId, String question, String content, int tokens, long elapsed, boolean success) {
        com.hfusionhub.entity.PromptTestCaseResultEntity e = new com.hfusionhub.entity.PromptTestCaseResultEntity();
        e.setId(caseId);
        e.setCaseId(caseId);
        e.setRunId(runId);
        e.setQuestion(question);
        e.setContent(content);
        e.setTokenCount(tokens);
        e.setElapsedMs(elapsed);
        e.setSuccess(success);
        return e;
    }

    /**
     * Minimal in-memory SaTokenContext for unit tests without a servlet container.
     */
    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> storage = new HashMap<>();

        @Override
        public SaRequest getRequest() { return mock(SaRequest.class); }

        @Override
        public SaResponse getResponse() { return mock(SaResponse.class); }

        @Override
        public SaStorage getStorage() {
            return new SaStorage() {
                @Override public Object getSource() { return storage; }
                @Override public Object get(String key) { return storage.get(key); }
                @Override public SaStorage set(String key, Object value) { storage.put(key, value); return this; }
                @Override public SaStorage delete(String key) { storage.remove(key); return this; }
            };
        }

        @Override public boolean matchPath(String pattern, String path) { return true; }
        @Override public boolean isValid() { return true; }
    }
}
