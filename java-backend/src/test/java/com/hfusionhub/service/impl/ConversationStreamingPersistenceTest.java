package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaTokenContextModelBox;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.hfusionhub.support.AbstractItMySQLTest;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStatusEvent;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.Message;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStatusEventMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.mapper.UsageCounterMapper;
import com.hfusionhub.mapper.UsageEventMapper;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.service.ConversationService;
import com.hfusionhub.service.MemoryService;
import com.hfusionhub.tenant.TenantContext;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

/**
 * 流式聊天持久化集成测试。
 *
 * <p>与 {@link ConversationStreamingUsageTest} 不同，本测试使用真实的
 * {@code AgentTaskService}（真实 Mapper + H2），断言流式路径中
 * 结构化 Agent 事件（step_completed / run_completed）与助手消息
 * 均成功落库，而非仅验证用量结算。</p>
 */
class ConversationStreamingPersistenceTest extends AbstractItMySQLTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @MockBean
    private AiClient aiClient;

    @MockBean
    private MemoryService memoryService;

    @Autowired
    private ConversationService conversationService;

    @Autowired
    private ConversationMapper conversationMapper;

    @Autowired
    private MessageMapper messageMapper;

    @Autowired
    private AgentTaskMapper agentTaskMapper;

    @Autowired
    private AgentRunMapper agentRunMapper;

    @Autowired
    private AgentStepMapper agentStepMapper;

    @Autowired
    private AgentStatusEventMapper agentStatusEventMapper;

    @Autowired
    private UsageEventMapper usageEventMapper;

    @Autowired
    private UsageReservationMapper usageReservationMapper;

    @Autowired
    private UsageCounterMapper usageCounterMapper;

    private Long conversationId;

    @BeforeEach
    void setUp() {
        // 无 Web 容器的 Spring 测试：安装内存 Sa-Token 上下文，使聊天链路的意图路由等
        // JwtUtils.getCurrentUserId() 调用可用（生产环境由请求线程提供上下文）
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());
        StpUtil.login(1L);

        // 异步 Reactor 线程无租户上下文，其写入盖 fail-closed 哨兵 tenant_id=-1；
        // 且 task↔run 互为 FK 环 + 逻辑删除行不会被 MP update/delete 命中——
        // 清理必须用 JdbcTemplate 裸 SQL（绕过逻辑删除条件），多轮重试
        for (int round = 0; round < 6; round++) {
            jdbcTemplate.update("UPDATE agent_task SET current_run_id = NULL WHERE current_run_id IS NOT NULL");
            try {
                jdbcTemplate.update("DELETE FROM agent_status_event");
                jdbcTemplate.update("DELETE FROM agent_step");
                jdbcTemplate.update("DELETE FROM agent_run");
                jdbcTemplate.update("DELETE FROM agent_task");
                jdbcTemplate.update("DELETE FROM message");
                jdbcTemplate.update("DELETE FROM conversation");
                jdbcTemplate.update("DELETE FROM usage_event");
                jdbcTemplate.update("DELETE FROM usage_reservation");
                jdbcTemplate.update("DELETE FROM usage_counter");
                break; // 清理成功
            } catch (DataIntegrityViolationException e) {
                // 上一用例的异步写库仍在进行（FK 竞态）：等待后重试
            }
            try {
                Thread.sleep(800);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        TenantContext.setTenantId(1L);
        Conversation conversation = new Conversation();
        conversation.setUserId(1L);
        conversation.setTitle("persist-stream-test");
        conversationMapper.insert(conversation);
        conversationId = conversation.getId();

        when(memoryService.getRelevantMemories(any(), any(), any(), anyInt())).thenReturn(List.of());
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
        TenantContext.clear();
    }

    /**
     * 异步流（content + step_completed + run_completed + [DONE]）在 Reactor 调度线程执行，
     * 断言：助手消息、agent_step、agent_run 终态、agent_status_event 全部真实落库。
     */
    @Test
    void asyncStreamPersistsAssistantMessageAndStructuredAgentEvents() {
        String requestId = "persist-1";
        String assistantRequestId = "persist-1:assistant";

        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"Hello persistence\"}\n\n",
                                "data: {\"event\":\"step_completed\",\"sequence\":1,"
                                        + "\"step_type\":\"retrieval\",\"action\":\"search\","
                                        + "\"input_summary\":\"q\",\"output_summary\":\"docs\"}\n\n",
                                "data: {\"event\":\"run_completed\",\"status\":\"completed\","
                                        + "\"tool_calls_count\":2,\"token_usage\":{\"prompt_tokens\":100,"
                                        + "\"completion_tokens\":40,\"total_tokens\":140}}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));;

        // 新增 8 参重载（对话图片输入）：与 7 参等价
        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"Hello persistence\"}\n\n",
                                "data: {\"event\":\"step_completed\",\"sequence\":1,"
                                        + "\"step_type\":\"retrieval\",\"action\":\"search\","
                                        + "\"input_summary\":\"q\",\"output_summary\":\"docs\"}\n\n",
                                "data: {\"event\":\"run_completed\",\"status\":\"completed\","
                                        + "\"tool_calls_count\":2,\"token_usage\":{\"prompt_tokens\":100,"
                                        + "\"completion_tokens\":40,\"total_tokens\":140}}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));

        MessageSendDTO dto = new MessageSendDTO();
        dto.setConversationId(conversationId);
        dto.setContent("hello world");
        dto.setRequestId(requestId);

        conversationService.sendMessageStream(dto, new SseEmitter(), 1L, new AtomicBoolean(false));

        // 异步等待：助手消息落库
        Message assistant = waitForAssistantMessage(assistantRequestId);
        assertNotNull(assistant, "assistant message should be persisted");
        assertEquals("assistant", assistant.getRole());
        assertEquals("Hello persistence", assistant.getContent());
        assertEquals(conversationId, assistant.getConversationId());

        // 结构化事件落库：agent_step（step_completed）
        AgentTask task = agentTaskMapper.selectByRequestId(requestId);
        assertNotNull(task, "agent_task should be persisted");

        List<AgentRun> runs = agentRunMapper.selectByTaskId(task.getId());
        assertFalse(runs.isEmpty(), "agent_run should be persisted");
        AgentRun run = waitForTerminalRun(runs.get(0).getId());
        assertEquals(AgentConstants.STATUS_SUCCEEDED, run.getStatus());
        assertEquals(Map.of("prompt_tokens", 100, "completion_tokens", 40, "total_tokens", 140), run.getTokenUsage());

        AgentStep step = agentStepMapper.selectOne(Wrappers.<AgentStep>lambdaQuery()
                .eq(AgentStep::getRunId, run.getId())
                .eq(AgentStep::getSequence, 1));
        assertNotNull(step, "agent_step from step_completed should be persisted");
        assertEquals("retrieval", step.getStepType());
        assertEquals("search", step.getAction());
        assertEquals("q", step.getInputSummary());
        assertEquals("docs", step.getOutputSummary());

        // 状态事件落库：STEP_RECORDED + RUN_SUCCEEDED
        List<AgentStatusEvent> events = agentStatusEventMapper.selectList(
                Wrappers.<AgentStatusEvent>lambdaQuery().eq(AgentStatusEvent::getTaskId, task.getId()));
        assertTrueContains(events, "STEP_RECORDED");
        assertTrueContains(events, "RUN_SUCCEEDED");
    }

    /**
     * 异步纯 content + [DONE] 流：与额度结算测试的最大区别是显式断言
     * 助手消息真实落库（现有结算测试仅发送 [DONE]、无 content）。
     * 本用例只关心消息持久化，不走任何结构化 Agent 事件。
     */
    @Test
    void asyncContentCompletionPersistsAssistantMessage() {
        String requestId = "persist-content-1";
        String assistantRequestId = "persist-content-1:assistant";

        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"Hello from pure content\"}\n\n",
                                "data: {\"content\":\" stream\"}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));;

        // 新增 8 参重载（对话图片输入）：与 7 参等价
        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"Hello from pure content\"}\n\n",
                                "data: {\"content\":\" stream\"}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));

        MessageSendDTO dto = new MessageSendDTO();
        dto.setConversationId(conversationId);
        dto.setContent("hello world");
        dto.setRequestId(requestId);

        conversationService.sendMessageStream(dto, new SseEmitter(), 1L, new AtomicBoolean(false));

        Message assistant = waitForAssistantMessage(assistantRequestId);
        assertNotNull(assistant, "assistant message should be persisted after content + [DONE]");
        assertEquals("assistant", assistant.getRole());
        // 两个 content chunk 顺序拼接
        assertEquals("Hello from pure content stream", assistant.getContent());
        assertEquals(conversationId, assistant.getConversationId());

        // 用户消息也应落库
        Message user = messageMapper.selectOne(
                Wrappers.<Message>lambdaQuery().eq(Message::getRole, "user").eq(Message::getRequestId, requestId));
        assertNotNull(user, "user message should be persisted");
        assertEquals("hello world", user.getContent());
    }

    /**
     * content_reset 桥接回归（第二十五批）：Python groundedness 重试路径发出的
     * {@code {"content_reset":true}} 无 event/content 键，Java 桥接层此前会
     * 静默丢弃——持久化内容变成"初稿+重试"拼接，前端气泡也不清空。
     * 修复后：重置持久化缓冲、转发清空事件，后续 content 分片替换重放。
     */
    @Test
    void asyncContentResetClearsAccumulatedContentAndForwardsResetEvent() {
        String requestId = "persist-reset-1";
        String assistantRequestId = "persist-reset-1:assistant";

        // 记录型 emitter：桥接层全部经 SseEventBuilder 发送，按次计数即可断言
        // （content×2 + content_reset + [DONE] = 4 次）；配合持久化断言构成回归 bite
        java.util.concurrent.atomic.AtomicInteger builderSends =
                new java.util.concurrent.atomic.AtomicInteger();
        SseEmitter recordingEmitter = new SseEmitter() {
            @Override
            public void send(SseEventBuilder builder) throws java.io.IOException {
                builderSends.incrementAndGet();
            }
        };

        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"幻觉初稿\"}\n\n",
                                "data: {\"content_reset\":true}\n\n",
                                "data: {\"content\":\"重试后的可信回答\"}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));
        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString(), anyLong(), any(), any()))
                .thenReturn(Flux.just(
                                "data: {\"content\":\"幻觉初稿\"}\n\n",
                                "data: {\"content_reset\":true}\n\n",
                                "data: {\"content\":\"重试后的可信回答\"}\n\n",
                                "data: [DONE]\n\n")
                        .subscribeOn(Schedulers.single()));

        MessageSendDTO dto = new MessageSendDTO();
        dto.setConversationId(conversationId);
        dto.setContent("hello world");
        dto.setRequestId(requestId);

        conversationService.sendMessageStream(dto, recordingEmitter, 1L, new AtomicBoolean(false));

        Message assistant = waitForAssistantMessage(assistantRequestId);
        assertNotNull(assistant, "assistant message should be persisted after reset + retry");
        // 核心回归断言：持久化内容只含重试后的文本（此前会拼接初稿）
        assertEquals("重试后的可信回答", assistant.getContent());
        // 前端桥接：content_reset 清空事件被转发（未修复时只有 3 次：content×2+[DONE]）
        assertEquals(4, builderSends.get(), "content_reset should be forwarded: content×2 + reset + [DONE]");
    }

    private Message waitForAssistantMessage(String assistantRequestId) {
        long deadline = System.currentTimeMillis() + 8000;
        Message assistant = null;
        while (System.currentTimeMillis() < deadline) {
            assistant = messageMapper.selectOne(Wrappers.<Message>lambdaQuery()
                    .eq(Message::getRole, "assistant")
                    .eq(Message::getRequestId, assistantRequestId));
            if (assistant != null) {
                return assistant;
            }
            sleep(50);
        }
        return null;
    }

    private AgentRun waitForTerminalRun(Long runId) {
        long deadline = System.currentTimeMillis() + 8000;
        while (System.currentTimeMillis() < deadline) {
            AgentRun run = agentRunMapper.selectById(runId);
            if (run != null && AgentConstants.isValidTerminalStatus(run.getStatus())) {
                return run;
            }
            sleep(50);
        }
        return agentRunMapper.selectById(runId);
    }

    private void assertTrueContains(List<AgentStatusEvent> events, String eventType) {
        boolean found = events.stream().anyMatch(e -> eventType.equals(e.getEventType()));
        org.junit.jupiter.api.Assertions.assertTrue(found, "expected status event " + eventType + " persisted");
    }

    private void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /** Minimal in-memory SaTokenContext for tests without a servlet container. */
    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> storage = new HashMap<>();
        private SaTokenContextModelBox modelBox;
    
        private MockSaTokenContext() {
            // 构造即装配 modelBox：SaManager.setSaTokenContext 之后立即可用
            setContext(mock(SaRequest.class), mock(SaResponse.class), new SaStorage() {
                @Override
                public Object getSource() {
                    return storage;
                }
    
                @Override
                public Object get(String key) {
                    return storage.get(key);
                }
    
                @Override
                public SaStorage set(String key, Object value) {
                    storage.put(key, value);
                    return this;
                }
    
                @Override
                public SaStorage delete(String key) {
                    storage.remove(key);
                    return this;
                }
            });
        }
    
        @Override
        public void setContext(SaRequest request, SaResponse response, SaStorage storage) {
            this.modelBox = new SaTokenContextModelBox(request, response, storage);
        }
    
        @Override
        public void clearContext() {
            this.modelBox = null;
        }
    
        @Override
        public boolean isValid() {
            return this.modelBox != null;
        }
    
        @Override
        public SaTokenContextModelBox getModelBox() {
            return this.modelBox;
        }
    }
}
