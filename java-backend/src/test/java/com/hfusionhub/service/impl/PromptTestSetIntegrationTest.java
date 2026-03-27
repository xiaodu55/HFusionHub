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
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetCompareRequest;
import com.hfusionhub.dto.PromptTestSetCompareResponse;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDTO;
import com.hfusionhub.dto.PromptTestSetRunDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetRunStatusDTO;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.dto.PromptTestCaseResult;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.PromptTestSetRunMapper;
import com.hfusionhub.mapper.UserMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Real-DB (H2) round-trip test for prompt test cases: save → read back →
 * variable substitution. Uses the real MyBatis-Plus mapper stack so the
 * {@link com.hfusionhub.handler.JsonMapTypeHandler} is exercised on both
 * write and read (autoResultMap). Redis is mocked (unused here); AiClient is
 * mocked so batch runs do not hit the Python service.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Transactional
class PromptTestSetIntegrationTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @MockBean
    private AiClient aiClient;

    @Autowired
    private PromptTestSetServiceImpl service;

    @Autowired
    private UserMapper userMapper;

    @Autowired
    private PromptTemplateMapper promptTemplateMapper;

    @Autowired
    private PromptTestSetRunMapper runMapper;

    @Autowired
    private PromptTestSetCaseWriter caseWriter;

    private Long userId;

    @BeforeEach
    void setUp() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        User user = new User();
        user.setUsername("pts-int-" + System.nanoTime());
        user.setPassword("test");
        user.setNickname("PTS");
        user.setStatus(0);
        userMapper.insert(user);
        userId = user.getId();

        StpUtil.login(userId);
    }

    private PromptTemplate createTemplate(String name, int version, String content) {
        PromptTemplate template = new PromptTemplate();
        template.setUserId(userId);
        template.setName(name);
        template.setContent(content);
        template.setVersion(version);
        template.setStatus(PromptTemplate.STATUS_PUBLISHED);
        promptTemplateMapper.insert(template);
        return template;
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    private PromptTestSetDetailDTO createSetWithCase(Map<String, Object> variables) {
        PromptTestSetSaveDTO setDto = new PromptTestSetSaveDTO();
        setDto.setName("回归集-" + System.nanoTime());
        PromptTestSetDetailDTO created = service.create(setDto);

        PromptTestCaseSaveDTO caseDto = new PromptTestCaseSaveDTO();
        caseDto.setQuestion("如何申请退款？");
        caseDto.setVariables(variables);
        service.addCase(created.getId(), caseDto);
        return created;
    }

    private PromptTestSetDetailDTO createSetWithRules(List<String> keywords, List<Long> docIds) {
        PromptTestSetSaveDTO setDto = new PromptTestSetSaveDTO();
        setDto.setName("规则集-" + System.nanoTime());
        PromptTestSetDetailDTO created = service.create(setDto);

        PromptTestCaseSaveDTO caseDto = new PromptTestCaseSaveDTO();
        caseDto.setQuestion("退款政策是什么？");
        caseDto.setExpectedKeywords(keywords);
        caseDto.setRequiredDocumentIds(docIds);
        service.addCase(created.getId(), caseDto);
        return created;
    }

    private PromptTestSetDetailDTO createSetWithCases(int n) {
        PromptTestSetSaveDTO setDto = new PromptTestSetSaveDTO();
        setDto.setName("并发集-" + System.nanoTime());
        PromptTestSetDetailDTO created = service.create(setDto);
        for (int i = 0; i < n; i++) {
            PromptTestCaseSaveDTO caseDto = new PromptTestCaseSaveDTO();
            caseDto.setQuestion("问题" + i);
            service.addCase(created.getId(), caseDto);
        }
        return created;
    }

    /** Submit then synchronously execute (queue is disabled in the test profile). */
    private PromptTestSetRunResponse runAndExecute(Long setId, PromptTestSetRunRequest request) {
        PromptTestSetRunStatusDTO status = service.run(setId, request);
        return service.executeRun(status.getId());
    }

    private PromptTestSetRunRequest request(String content) {
        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent(content);
        return request;
    }

    @Test
    void saveThenReadBackRestoresVariablesMap() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("role", "客服");
        vars.put("topic", "退款");
        vars.put("变量", "中文值");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        // Read back through the real mapper + JsonMapTypeHandler (autoResultMap)
        PromptTestSetDetailDTO detail = service.getDetail(created.getId());

        assertEquals(1, detail.getCases().size());
        PromptTestCaseDTO tc = detail.getCases().get(0);
        assertNotNull(tc.getVariables(), "variables should be restored from DB as a Map");
        assertEquals("客服", tc.getVariables().get("role"));
        assertEquals("退款", tc.getVariables().get("topic"));
        assertEquals("中文值", tc.getVariables().get("变量"));
    }

    @Test
    void readBackThenBatchRunSubstitutesVariables() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        vars.put("主题", "退款");
        vars.put("topic", "RAG");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(10);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是{{角色}}，关于{{主题}}（{{topic}}）请回答");
        PromptTestSetRunResponse result = runAndExecute(created.getId(), request);

        assertEquals(1, result.getTotalCases());
        assertEquals(1, result.getSuccessCount());
        assertEquals("你是客服，关于退款（RAG）请回答", result.getResults().get(0).getRenderedTemplate());
    }

    @Test
    void updateCasePersistsNewVariablesAndReadsBack() {
        PromptTestSetDetailDTO created = createSetWithCase(new HashMap<>(Map.of("role", "客服")));
        Long caseId = service.getDetail(created.getId()).getCases().get(0).getId();

        PromptTestCaseSaveDTO updateDto = new PromptTestCaseSaveDTO();
        updateDto.setQuestion("改后问题");
        Map<String, Object> newVars = new HashMap<>();
        newVars.put("变量", "新值");
        newVars.put("num", 42);
        updateDto.setVariables(newVars);
        service.updateCase(created.getId(), caseId, updateDto);

        PromptTestSetDetailDTO detail = service.getDetail(created.getId());
        PromptTestCaseDTO tc = detail.getCases().get(0);
        assertEquals("改后问题", tc.getQuestion());
        assertEquals("新值", tc.getVariables().get("变量"));
        assertEquals(42, tc.getVariables().get("num"));
    }

    @Test
    void runPersistsHistoryAndReadsBack() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        PromptTemplate template = createTemplate("客服模板", 7, "你是{{角色}}，请回答");

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答内容");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(88);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateId(template.getId());
        request.setTemplateVersion(99);
        request.setTemplateName("伪造名称");
        PromptTestSetRunResponse runResponse = runAndExecute(created.getId(), request);

        assertNotNull(runResponse.getRunId());
        assertEquals(template.getId(), runResponse.getTemplateId());
        assertEquals(7, runResponse.getTemplateVersion());
        assertEquals("客服模板", runResponse.getTemplateName());

        // Run history lists the persisted run
        List<PromptTestSetRunDTO> runs = service.listRuns(created.getId());
        assertEquals(1, runs.size());
        assertEquals(runResponse.getRunId(), runs.get(0).getId());
        assertEquals(7, runs.get(0).getTemplateVersion());
        assertEquals("客服模板", runs.get(0).getTemplateName());
        assertEquals(1, runs.get(0).getTotalCases());
        assertEquals(1, runs.get(0).getSuccessCount());

        // Run detail restores per-case result incl. JSON token usage/sources
        PromptTestSetRunDetailDTO detail = service.getRunDetail(runResponse.getRunId());
        assertEquals(1, detail.getResults().size());
        assertEquals("回答内容", detail.getResults().get(0).getContent());
        assertEquals(88, detail.getResults().get(0).getTokenCount());
    }

    @Test
    void runWithBoundTemplateUsesDbContentDespiteEditedPayload() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        PromptTemplate template = createTemplate("客服模板", 7, "你是{{角色}}，来自模板");

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答内容");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(88);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        // Edited/payload content must be ignored when a template is bound
        request.setTemplateId(template.getId());
        request.setTemplateContent("被篡改的自定义内容");
        request.setTemplateName("伪造名称");
        runAndExecute(created.getId(), request);

        List<PromptTestSetRunDTO> runs = service.listRuns(created.getId());
        assertEquals(1, runs.size());
        assertEquals("客服模板", runs.get(0).getTemplateName());
        assertEquals(7, runs.get(0).getTemplateVersion());
        assertTrue(runs.get(0).getTemplateContent().contains("来自模板"));

        // Rendered template must use the DB snapshot content
        PromptTestSetRunDetailDTO detail = service.getRunDetail(runs.get(0).getId());
        assertEquals("你是客服，来自模板", detail.getResults().get(0).getRenderedTemplate());
    }

    @Test
    void runRejectsForeignTemplate() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        // Template owned by another user (impersonation attempt)
        User other = new User();
        other.setUsername("pts-other-" + System.nanoTime());
        other.setPassword("test");
        other.setNickname("OTHER");
        other.setStatus(0);
        userMapper.insert(other);

        PromptTemplate foreign = new PromptTemplate();
        foreign.setUserId(other.getId());
        foreign.setName("他人模板");
        foreign.setContent("你不是我");
        foreign.setVersion(1);
        foreign.setStatus(PromptTemplate.STATUS_PUBLISHED);
        promptTemplateMapper.insert(foreign);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("模板");
        request.setTemplateId(foreign.getId());

        com.hfusionhub.common.exception.BusinessException ex = assertThrows(
                com.hfusionhub.common.exception.BusinessException.class,
                () -> service.run(created.getId(), request));
        assertTrue(ex.getMessage().contains("无权"));
        assertEquals(0, service.listRuns(created.getId()).size());
    }

    @Test
    void compareTwoTemplateVersionsPerCase() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("主题", "退款");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        PromptTemplate tpl1 = createTemplate("对比模板v1", 1, "v1 模板：{{主题}}");
        PromptTemplate tpl2 = createTemplate("对比模板v2", 2, "v2 模板：{{主题}}");

        AiClient.ChatResponse resp1 = new AiClient.ChatResponse();
        resp1.setContent("回答 v1");
        resp1.setModel("deepseek-v4-flash");
        resp1.setTokenCount(10);
        AiClient.ChatResponse resp2 = new AiClient.ChatResponse();
        resp2.setContent("回答 v2");
        resp2.setModel("deepseek-v4-flash");
        resp2.setTokenCount(20);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString()))
                .thenReturn(resp1)
                .thenReturn(resp2);

        PromptTestSetRunRequest req1 = new PromptTestSetRunRequest();
        req1.setTemplateId(tpl1.getId());
        PromptTestSetRunResponse run1 = runAndExecute(created.getId(), req1);

        PromptTestSetRunRequest req2 = new PromptTestSetRunRequest();
        req2.setTemplateId(tpl2.getId());
        PromptTestSetRunResponse run2 = runAndExecute(created.getId(), req2);

        PromptTestSetCompareRequest compareRequest = new PromptTestSetCompareRequest();
        compareRequest.setRunIdA(run1.getRunId());
        compareRequest.setRunIdB(run2.getRunId());
        PromptTestSetCompareResponse compare = service.compare(compareRequest);

        assertEquals(1, compare.getRunA().getTemplateVersion());
        assertEquals(2, compare.getRunB().getTemplateVersion());
        assertEquals(1, compare.getComparedCases());
        assertEquals(1, compare.getComparisons().size());
        assertEquals("回答 v1", compare.getComparisons().get(0).getResultA().getContent());
        assertEquals("回答 v2", compare.getComparisons().get(0).getResultB().getContent());
        assertEquals(Boolean.FALSE, compare.getComparisons().get(0).getAnswerIdentical());
    }

    @Test
    void passRulesRoundTripThroughDb() {
        PromptTestSetDetailDTO created = createSetWithRules(List.of("退款", "7天"), List.of(11L, 22L));

        PromptTestSetDetailDTO detail = service.getDetail(created.getId());
        PromptTestCaseDTO tc = detail.getCases().get(0);
        assertEquals(List.of("退款", "7天"), tc.getExpectedKeywords());
        assertEquals(List.of(11L, 22L), tc.getRequiredDocumentIds());
    }

    @Test
    void runEvaluatesAndPersistsPassRules() {
        PromptTestSetDetailDTO created = createSetWithRules(List.of("退款", "7天"), List.of(11L, 22L));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("7天内支持退款，请参考政策。");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(30);
        resp.setSources(List.of(
                Map.of("document_id", 11L, "chunk_id", "c1"),
                Map.of("document_id", 22L, "chunk_id", "c2")
        ));
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是客服助手");
        PromptTestSetRunResponse runResponse = runAndExecute(created.getId(), request);

        assertEquals(1, runResponse.getPassCount());
        assertEquals(100.0, runResponse.getPassRate());
        assertTrue(runResponse.getResults().get(0).isPassed());

        List<PromptTestSetRunDTO> runs = service.listRuns(created.getId());
        assertEquals(1, runs.get(0).getPassCount());
        assertEquals(100.0, runs.get(0).getPassRate());

        PromptTestSetRunDetailDTO detail = service.getRunDetail(runResponse.getRunId());
        assertTrue(detail.getResults().get(0).isPassed());
    }

    @Test
    void runRecordsPassNotesWhenRuleFails() {
        PromptTestSetDetailDTO created = createSetWithRules(List.of("退款", "7天"), List.of(11L, 22L));

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("请拨打400咨询。");
        resp.setModel("deepseek-v4-flash");
        resp.setTokenCount(30);
        resp.setSources(List.of(Map.of("document_id", 11L, "chunk_id", "c1")));
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是客服助手");
        PromptTestSetRunResponse runResponse = runAndExecute(created.getId(), request);

        assertEquals(0, runResponse.getPassCount());
        assertEquals(0.0, runResponse.getPassRate());

        // persisted pass_notes survive the round trip
        PromptTestSetRunDetailDTO detail = service.getRunDetail(runResponse.getRunId());
        PromptTestCaseResult persisted = detail.getResults().get(0);
        assertFalse(persisted.isPassed());
        assertNotNull(persisted.getPassNotes());
        assertTrue(persisted.getPassNotes().stream().anyMatch(n -> n.contains("7天")));
        assertTrue(persisted.getPassNotes().stream().anyMatch(n -> n.contains("22")));
    }

    @Test
    void compareReportsPassRatePerVersion() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("主题", "退款");
        PromptTestSetDetailDTO created = createSetWithRules(List.of("退款"), List.of());

        PromptTemplate tpl1 = createTemplate("通过模板", 1, "v1 模板：{{主题}}");
        PromptTemplate tpl2 = createTemplate("失败模板", 2, "v2 模板：{{主题}}");

        AiClient.ChatResponse resp1 = new AiClient.ChatResponse();
        resp1.setContent("我们支持退款流程。");
        resp1.setModel("deepseek-v4-flash");
        resp1.setTokenCount(10);
        AiClient.ChatResponse resp2 = new AiClient.ChatResponse();
        resp2.setContent("请联系客服。");
        resp2.setModel("deepseek-v4-flash");
        resp2.setTokenCount(20);
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString()))
                .thenReturn(resp1)
                .thenReturn(resp2);

        PromptTestSetRunRequest req1 = new PromptTestSetRunRequest();
        req1.setTemplateId(tpl1.getId());
        PromptTestSetRunResponse run1 = runAndExecute(created.getId(), req1);

        PromptTestSetRunRequest req2 = new PromptTestSetRunRequest();
        req2.setTemplateId(tpl2.getId());
        PromptTestSetRunResponse run2 = runAndExecute(created.getId(), req2);

        PromptTestSetCompareRequest compareRequest = new PromptTestSetCompareRequest();
        compareRequest.setRunIdA(run1.getRunId());
        compareRequest.setRunIdB(run2.getRunId());
        PromptTestSetCompareResponse compare = service.compare(compareRequest);

        assertEquals(100.0, compare.getRunA().getPassRate());
        assertEquals(0.0, compare.getRunB().getPassRate());
        assertTrue(compare.getComparisons().get(0).getResultA().isPassed());
        assertFalse(compare.getComparisons().get(0).getResultB().isPassed());
    }

    // ── Async lifecycle (queue / progress / cancel / retry) ───────────

    @Test
    void queuedRunThenExecutePersistsStatusAndProgress() {
        Map<String, Object> vars = new HashMap<>();
        vars.put("角色", "客服");
        PromptTestSetDetailDTO created = createSetWithCase(vars);

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        resp.setModel("deepseek-v4-flash");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunRequest request = new PromptTestSetRunRequest();
        request.setTemplateContent("你是{{角色}}");

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request);
        assertEquals("pending", queued.getStatus());
        assertEquals(1, queued.getTotalCases());
        assertEquals(0, queued.getProgressCount());

        // The queued run is visible to the worker queue
        assertEquals(1, service.listQueuedRuns(10).stream()
                .filter(r -> r.getId().equals(queued.getId())).count());
        assertTrue(service.claimRun(queued.getId()));
        // Guarded claim: second attempt fails because it is already running
        assertFalse(service.claimRun(queued.getId()));

        service.executeRun(queued.getId());

        PromptTestSetRunStatusDTO done = service.getRunStatus(queued.getId());
        assertEquals("succeeded", done.getStatus());
        assertEquals(1, done.getProgressCount());
        assertEquals(1, done.getSuccessCount());
        assertEquals(100.0, done.getPassRate());
        assertNotNull(done.getStartedAt());
        assertNotNull(done.getCompletedAt());
    }

    @Test
    void cancelPendingRunRemovesFromQueue() {
        PromptTestSetDetailDTO created = createSetWithCase(new HashMap<>(Map.of("角色", "客服")));

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        PromptTestSetRunStatusDTO cancelled = service.cancelRun(queued.getId());
        assertEquals("cancelled", cancelled.getStatus());

        // Cancelled run is no longer queued and won't execute
        assertEquals(0, service.listQueuedRuns(10).stream()
                .filter(r -> r.getId().equals(queued.getId())).count());
        assertFalse(service.claimRun(queued.getId()));
        assertNull(service.executeRun(queued.getId()));

        // History still records the cancelled run
        assertEquals(1, service.listRuns(created.getId()).size());
    }

    @Test
    void failedRunCanBeRetriedWithNextAttempt() {
        PromptTestSetDetailDTO created = createSetWithCase(new HashMap<>(Map.of("角色", "客服")));

        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString()))
                .thenThrow(new RuntimeException("boom"));

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        service.executeRun(queued.getId());

        PromptTestSetRunStatusDTO failed = service.getRunStatus(queued.getId());
        assertEquals("succeeded", failed.getStatus());
        assertEquals(1, failed.getFailureCount());
        assertEquals(0, failed.getSuccessCount());

        // Retry re-queues (attempt 2) and clears previous results
        PromptTestSetRunStatusDTO requeued = service.retryRun(queued.getId());
        assertEquals("pending", requeued.getStatus());
        assertEquals(2, requeued.getAttemptNumber());

        // Now the AI succeeds → batch completes (doReturn to avoid replaying the throwing stub)
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        doReturn(resp).when(aiClient).chat(anyString(), isNull(), isNull(), any(), anyString());
        service.executeRun(queued.getId());

        PromptTestSetRunStatusDTO done = service.getRunStatus(queued.getId());
        assertEquals("succeeded", done.getStatus());
        assertEquals(2, done.getAttemptNumber());
        assertEquals(1, done.getSuccessCount());
        assertEquals(0, done.getFailureCount());

        // Run detail reflects only the retried results (old ones cleared)
        assertEquals(1, service.getRunDetail(queued.getId()).getResults().size());
    }

    @Test
    void recoveryMarksStaleRunningRunAsFailed() throws Exception {
        PromptTestSetDetailDTO created = createSetWithCase(new HashMap<>(Map.of("角色", "客服")));

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        assertTrue(service.claimRun(queued.getId()));

        // Simulate a worker that died mid-run: started long ago, still running
        PromptTestSetRun stale = new PromptTestSetRun();
        stale.setId(queued.getId());
        stale.setStatus("running");
        stale.setStartedAt(java.time.LocalDateTime.now().minusMinutes(120));
        runMapper.update(null, new com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getId, queued.getId())
                .set(PromptTestSetRun::getStatus, "running")
                .set(PromptTestSetRun::getStartedAt, java.time.LocalDateTime.now().minusMinutes(120)));

        int marked = service.markStaleRunsFailed(30);
        assertEquals(1, marked);

        PromptTestSetRunStatusDTO recovered = service.getRunStatus(queued.getId());
        assertEquals("failed", recovered.getStatus());
        assertNotNull(recovered.getErrorMessage());
    }

    // ── Concurrency: cancel→retry and cross-instance isolation ────────

    /**
     * 取消执行中的任务后「立即重试」：retry 重新生成 execution_token，因此仍在
     * AI 调用中阻塞的旧 Worker 在释放后第一次守卫写入（进度推进）即失效并中止，
     * 不会把结果写入新一轮任务，也不会覆盖新一轮的 pending 状态。
     *
     * <p>此测试使用真实的 H2 + MyBatis-Plus（守卫更新为原子 SQL），且主线程与
     * Worker 线程分别自动提交，以还原生产环境的并发时序。
     */
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void cancelThenImmediateRetryIsolatesStaleWorker() throws Exception {
        PromptTestSetDetailDTO created = createSetWithCases(3);

        AtomicInteger calls = new AtomicInteger();
        CountDownLatch workerInChat = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenAnswer(inv -> {
            if (calls.incrementAndGet() == 1) {
                workerInChat.countDown();
                releaseWorker.await(10, TimeUnit.SECONDS);
            }
            return resp;
        });

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        Long runId = queued.getId();
        assertTrue(service.claimRun(runId));
        String tokenBefore = runMapper.selectById(runId).getExecutionToken();
        assertNotNull(tokenBefore);

        // 旧 Worker 启动并在首个 AI 调用内阻塞。
        AtomicReference<Throwable> workerError = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                service.executeRun(runId);
            } catch (Throwable t) {
                workerError.set(t);
            }
        }, "pts-stale-worker");
        worker.start();
        assertTrue(workerInChat.await(10, TimeUnit.SECONDS), "worker never entered AI call");

        // 取消执行中的任务，然后立刻重试（attempt 2，重新生成 token）。
        PromptTestSetRunStatusDTO cancelled = service.cancelRun(runId);
        assertEquals("cancelled", cancelled.getStatus());
        PromptTestSetRunStatusDTO requeued = service.retryRun(runId);
        assertEquals("pending", requeued.getStatus());
        assertEquals(2, requeued.getAttemptNumber());
        String tokenAfter = runMapper.selectById(runId).getExecutionToken();
        assertNotNull(tokenAfter);
        assertNotEquals("retry must regenerate the execution token", tokenBefore, tokenAfter);

        // 释放旧 Worker：其守卫式进度写入因 token 不匹配命中 0 行而中止。
        releaseWorker.countDown();
        worker.join(10_000);
        assertFalse(worker.isAlive());
        assertNull(workerError.get());

        // 旧 Worker 没有污染新一轮：run 保持 pending（新 token），进度 0，无任何结果。
        assertEquals("pending", runMapper.selectById(runId).getStatus());
        assertEquals(0, runMapper.selectById(runId).getProgressCount());
        assertEquals(0, service.getRunDetail(runId).getResults().size());
        assertEquals(1, calls.get(), "stale worker must abort after exactly one AI call");

        // 新一轮完整执行（attempt 2），结果数与成功数完全来自本轮，无串扰。
        PromptTestSetRunResponse done = service.executeRun(runId);
        assertEquals(3, done.getSuccessCount());
        PromptTestSetRunStatusDTO status = service.getRunStatus(runId);
        assertEquals("succeeded", status.getStatus());
        assertEquals(2, status.getAttemptNumber());
        assertEquals(3, service.getRunDetail(runId).getResults().size());

        service.delete(created.getId());
    }

    /**
     * 跨实例取消：Worker A（实例 A）正在执行，实例 B 的取消操作仅把 DB 状态置为
     * CANCELLED（B 的 cancelledRuns 内存标志对 A 不可见）。A 在下一个守卫写入
     * （状态离开 pending/running）时失效并中止，不产生重复 AI 调用或脏结果。
     */
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void crossInstanceCancelStopsStaleWorkerViaGuardedWrites() throws Exception {
        PromptTestSetDetailDTO created = createSetWithCases(3);

        AtomicInteger calls = new AtomicInteger();
        CountDownLatch workerInChat = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenAnswer(inv -> {
            if (calls.incrementAndGet() == 1) {
                workerInChat.countDown();
                releaseWorker.await(10, TimeUnit.SECONDS);
            }
            return resp;
        });

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        Long runId = queued.getId();
        assertTrue(service.claimRun(runId));

        AtomicReference<Throwable> workerError = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                service.executeRun(runId);
            } catch (Throwable t) {
                workerError.set(t);
            }
        }, "pts-worker-A");
        worker.start();
        assertTrue(workerInChat.await(10, TimeUnit.SECONDS), "worker never entered AI call");

        // 模拟实例 B 取消：直接翻转 DB 状态，B 的 cancelledRuns 标志对 A 不可见。
        // 与真实跨实例取消一致——隔离完全依赖 DB 上的守卫写入。
        runMapper.update(null, new com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getId, runId)
                .eq(PromptTestSetRun::getStatus, PromptTestSetRunStatus.RUNNING)
                .set(PromptTestSetRun::getStatus, PromptTestSetRunStatus.CANCELLED)
                .set(PromptTestSetRun::getCompletedAt, java.time.LocalDateTime.now()));

        releaseWorker.countDown();
        worker.join(10_000);
        assertFalse(worker.isAlive());
        assertNull(workerError.get());

        // Worker A 在下一个守卫写入中止：状态保持 cancelled，无结果写入，无多余 AI 调用。
        assertEquals("cancelled", runMapper.selectById(runId).getStatus());
        assertEquals(0, runMapper.selectById(runId).getProgressCount());
        assertEquals(0, service.getRunDetail(runId).getResults().size());
        assertEquals(1, calls.get(), "worker must not keep calling AI after cross-instance cancel");

        service.delete(created.getId());
    }

    /**
     * 「进度已写、结果未写」窗口：worker 的原子写事务在「守卫更新成功（进度已写、未提交、
     * 已持有 run 行 X 锁）」与「结果插入」之间被钩子卡住。此时取消+重试必须阻塞在 worker
     * 事务持有的锁上；worker 提交后重试执行并清除其提交的结果。最终无残留脏数据、run 回到
     * pending + 新 token，旧 Worker 不再发起额外 AI 调用。
     *
     * <p>该窗口在未原子化实现下会让旧 Worker 无条件插入旧 token 的结果行（DB 残留脏数据）；
     * 原子化后由「单事务 + 行锁互斥」彻底消除。
     */
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void atomicWriteSerializesAgainstRetry_noDirtyResultsInProgressWrittenWindow() throws Exception {
        PromptTestSetDetailDTO created = createSetWithCases(1);

        CountDownLatch inWindow = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        CountDownLatch cancelDone = new CountDownLatch(1);
        AtomicReference<Throwable> cancelError = new AtomicReference<>();

        AiClient.ChatResponse resp = new AiClient.ChatResponse();
        resp.setContent("回答");
        when(aiClient.chat(anyString(), isNull(), isNull(), any(), anyString())).thenReturn(resp);

        PromptTestSetRunStatusDTO queued = service.run(created.getId(), request("你是{{角色}}"));
        Long runId = queued.getId();
        assertTrue(service.claimRun(runId));
        String tokenBefore = runMapper.selectById(runId).getExecutionToken();
        assertNotNull(tokenBefore);

        // 在「进度已写、结果未写」窗口同步点注入阻塞（生产环境该钩子为空，不改变行为）。
        Object originalHook = ReflectionTestUtils.getField(caseWriter, "caseWriteHook");
        ReflectionTestUtils.setField(caseWriter, "caseWriteHook",
                (PromptTestSetCaseWriter.CaseWriteHook) () -> {
                    inWindow.countDown();
                    try {
                        releaseWorker.await(10, TimeUnit.SECONDS);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
        try {
            Thread worker = new Thread(() -> {
                try {
                    service.executeRun(runId);
                } catch (Throwable t) {
                    // 忽略——由主线程断言负责
                }
            }, "pts-window-worker");
            worker.start();

            assertTrue(inWindow.await(10, TimeUnit.SECONDS),
                    "worker never reached the progress-written window");

            // 取消+重试在另一线程执行：worker 事务持有 run 行 X 锁，二者必须阻塞到 worker 提交。
            Thread cancelThread = new Thread(() -> {
                try {
                    service.cancelRun(runId);
                    service.retryRun(runId);
                } catch (Throwable t) {
                    cancelError.set(t);
                } finally {
                    cancelDone.countDown();
                }
            }, "pts-window-cancel");
            cancelThread.start();

            // 互斥验证：worker 事务未提交时，取消+重试不得提前完成。
            Thread.sleep(300);
            assertFalse(cancelDone.await(50, TimeUnit.MILLISECONDS),
                    "cancel/retry must block on the worker's active transaction");

            // 释放 worker → 结果插入并提交事务 → 重试随后执行并清除其结果。
            releaseWorker.countDown();
            worker.join(10_000);
            cancelThread.join(10_000);
            assertFalse(worker.isAlive());
            assertNull(cancelError.get());

            // 无残留：重试已清除 worker 提交的结果行；run 回到 pending + 新 token + attempt 2。
            assertEquals(0, service.getRunDetail(runId).getResults().size());
            PromptTestSetRun fresh = runMapper.selectById(runId);
            assertEquals("pending", fresh.getStatus());
            assertEquals(2, fresh.getAttemptNumber());
            assertEquals(0, fresh.getProgressCount());
            assertNotEquals(tokenBefore, fresh.getExecutionToken());
            // 旧 Worker 只发起了这一次 AI 调用（唯一用例提交后即因守卫失效而中止）。
            verify(aiClient, times(1)).chat(anyString(), isNull(), isNull(), any(), anyString());
        } finally {
            ReflectionTestUtils.setField(caseWriter, "caseWriteHook", originalHook);
            service.delete(created.getId());
        }
    }

    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> store = new HashMap<>();
        @Override public SaRequest getRequest() { return mock(SaRequest.class); }
        @Override public SaResponse getResponse() { return mock(SaResponse.class); }
        @Override public SaStorage getStorage() {
            return new SaStorage() {
                @Override public Object getSource() { return store; }
                @Override public Object get(String k) { return store.get(k); }
                @Override public SaStorage set(String k, Object v) { store.put(k, v); return this; }
                @Override public SaStorage delete(String k) { store.remove(k); return this; }
            };
        }
        @Override public boolean matchPath(String p, String path) { return true; }
        @Override public boolean isValid() { return true; }
    }
}
