package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.dto.OpenApiBidCheckResponse;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.AppApiKey;
import com.hfusionhub.mapper.AppApiKeyMapper;
import com.hfusionhub.mapper.AppCallLogMapper;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.service.BidCheckService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OpenApiServiceImplTest {

    @Mock
    private AppMapper appMapper;

    @Mock
    private AppApiKeyMapper apiKeyMapper;

    @Mock
    private AppCallLogMapper callLogMapper;

    @Mock
    private AiClient aiClient;

    @Mock
    private RedisUtils redisUtils;

    @Mock
    private BidCheckService bidCheckService;

    @InjectMocks
    private OpenApiServiceImpl openApiService;

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return toHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private AppApiKey enabledKey(String secret, long keyId, long appId) {
        AppApiKey key = new AppApiKey();
        key.setId(keyId);
        key.setAppId(appId);
        key.setKeyHash(sha256(secret));
        key.setEnabled(1);
        return key;
    }

    private App publishedApp(long id) {
        App app = new App();
        app.setId(id);
        app.setName("客服助手");
        app.setUserId(1L);
        app.setTenantId(1L);
        app.setKnowledgeBaseId(10L);
        app.setStyle("detailed");
        app.setStatus(1);
        return app;
    }

    @Test
    void missingApiKeyIsRejected() {
        assertThrows(BusinessException.class, () -> openApiService.chat(null, new OpenApiChatRequest()));
    }

    @Test
    void invalidApiKeyIsRejected() {
        when(apiKeyMapper.selectOne(any())).thenReturn(null);

        OpenApiChatRequest request = new OpenApiChatRequest();
        request.setQuery("你好");

        BusinessException ex =
                assertThrows(BusinessException.class, () -> openApiService.chat("hf_invalidkey", request));
        assertEquals(401, ex.getCode());
    }

    @Test
    void unpublishedAppIsRejected() {
        String secret = "***REMOVED-BY-REWRITE***";
        AppApiKey key = enabledKey(secret, 1L, 1L);
        App app = publishedApp(1L);
        app.setStatus(0); // draft
        when(apiKeyMapper.selectOne(any())).thenReturn(key);
        when(appMapper.selectById(1L)).thenReturn(app);

        OpenApiChatRequest request = new OpenApiChatRequest();
        request.setQuery("你好");

        BusinessException ex = assertThrows(BusinessException.class, () -> openApiService.chat(secret, request));
        assertEquals(403, ex.getCode());
    }

    @Test
    void rateLimitedReturns429() {
        String secret = "***REMOVED-BY-REWRITE***";
        when(apiKeyMapper.selectOne(any())).thenReturn(enabledKey(secret, 1L, 1L));
        when(appMapper.selectById(1L)).thenReturn(publishedApp(1L));
        when(redisUtils.increment(anyString(), anyLong())).thenReturn(999L); // over limit

        OpenApiChatRequest request = new OpenApiChatRequest();
        request.setQuery("你好");

        BusinessException ex = assertThrows(BusinessException.class, () -> openApiService.chat(secret, request));
        assertEquals(429, ex.getCode());
        verify(callLogMapper).insert(any());
    }

    @Test
    void validCallReturnsAnswerAndRecordsUsage() {
        String secret = "***REMOVED-BY-REWRITE***";
        when(apiKeyMapper.selectOne(any())).thenReturn(enabledKey(secret, 1L, 1L));
        when(appMapper.selectById(1L)).thenReturn(publishedApp(1L));
        when(redisUtils.increment(anyString(), anyLong())).thenReturn(1L);

        AiClient.ChatResponse ai = new AiClient.ChatResponse();
        ai.setContent("客服答复内容");
        ai.setModel("deepseek-v4-flash");
        ai.setStatus("completed");
        ai.setTokenCount(120);
        ai.setTokenUsage(Map.of("prompt_tokens", 80, "completion_tokens", 40, "total_tokens", 120));
        when(aiClient.agentV1Chat(
                        anyString(), any(), any(), any(), anyString(), anyInt(), anyString(), anyLong(), any(), any()))
                .thenReturn(ai);

        OpenApiChatRequest request = new OpenApiChatRequest();
        request.setQuery("退货政策是什么？");
        request.setHistory(List.of(Map.of("role", "user", "content", "hi")));

        OpenApiChatResponse response = openApiService.chat(secret, request);

        assertEquals("客服答复内容", response.getContent());
        assertEquals("completed", response.getStatus());
        verify(aiClient)
                .agentV1Chat(
                        eq("退货政策是什么？"),
                        isNull(),
                        eq(10L),
                        any(),
                        eq("detailed"),
                        anyInt(),
                        anyString(),
                        eq(1L),
                        any(),
                        any());
        verify(callLogMapper).insert(any());
    }

    // ── /openapi/bid/check（P2-7）──────────────────────────────

    @Test
    void bidCheckRunsUnderAppTenantAndReturnsSummary() {
        String secret = "***REMOVED-BY-REWRITE***";
        when(apiKeyMapper.selectOne(any())).thenReturn(enabledKey(secret, 2L, 1L));
        when(appMapper.selectById(1L)).thenReturn(publishedApp(1L));
        when(redisUtils.increment(anyString(), anyLong())).thenReturn(1L);
        when(bidCheckService.checkForApi(anyLong(), eq(1L)))
                .thenReturn(Map.of("total", 3, "critical", 1, "warning", 1, "info", 1));

        OpenApiBidCheckResponse response = openApiService.bidCheck(secret, 5L);

        assertEquals("ok", response.getStatus());
        assertEquals(5L, response.getProjectId());
        assertEquals(1, response.getSummary().get("critical"));
        // 以应用所属租户 1 执行自检
        verify(bidCheckService).checkForApi(5L, 1L);
        verify(callLogMapper).insert(any());
    }

    @Test
    void bidCheckMissingProjectIdRejected() {
        BusinessException ex = assertThrows(BusinessException.class, () -> openApiService.bidCheck("hf_xxx", null));
        assertEquals(400, ex.getCode());
    }

    @Test
    void bidCheckPropagatesModuleGateForbidden() {
        String secret = "***REMOVED-BY-REWRITE***";
        when(apiKeyMapper.selectOne(any())).thenReturn(enabledKey(secret, 2L, 1L));
        when(appMapper.selectById(1L)).thenReturn(publishedApp(1L));
        when(redisUtils.increment(anyString(), anyLong())).thenReturn(1L);
        doThrow(new BusinessException(403, "投标开放 API 需要开通「投标开放 API」模块，请在套餐中心升级后重试"))
                .when(bidCheckService).checkForApi(5L, 1L);

        BusinessException ex = assertThrows(BusinessException.class, () -> openApiService.bidCheck(secret, 5L));

        assertEquals(403, ex.getCode());
        verify(callLogMapper).insert(any()); // 失败也记录调用
    }
}
