package com.hfusionhub.service.impl;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.entity.User;
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
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.isNull;
import static org.mockito.Mockito.mock;
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
        PromptTestSetRunResponse result = service.run(created.getId(), request);

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
