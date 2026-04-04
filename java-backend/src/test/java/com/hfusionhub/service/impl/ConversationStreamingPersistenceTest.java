package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
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
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

/**
 * 流式聊天持久化集成测试。
 *
 * <p>与 {@link ConversationStreamingUsageTest} 不同，本测试使用真实的
 * {@code AgentTaskService}（真实 Mapper + H2），断言流式路径中
 * 结构化 Agent 事件（step_completed / run_completed）与助手消息
 * 均成功落库，而非仅验证用量结算。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class ConversationStreamingPersistenceTest {

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
        // 清理顺序遵循 FK：status_event → step → run → task → message → conversation
        agentStatusEventMapper.delete(Wrappers.emptyWrapper());
        agentStepMapper.delete(Wrappers.emptyWrapper());
        agentRunMapper.delete(Wrappers.emptyWrapper());
        agentTaskMapper.delete(Wrappers.emptyWrapper());
        messageMapper.delete(Wrappers.emptyWrapper());
        conversationMapper.delete(Wrappers.emptyWrapper());
        usageEventMapper.delete(Wrappers.emptyWrapper());
        usageReservationMapper.delete(Wrappers.emptyWrapper());
        usageCounterMapper.delete(Wrappers.emptyWrapper());

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

        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString()))
                .thenReturn(Flux.just(
                        "data: {\"content\":\"Hello persistence\"}\n\n",
                        "data: {\"event\":\"step_completed\",\"sequence\":1,"
                                + "\"step_type\":\"retrieval\",\"action\":\"search\","
                                + "\"input_summary\":\"q\",\"output_summary\":\"docs\"}\n\n",
                        "data: {\"event\":\"run_completed\",\"status\":\"completed\","
                                + "\"tool_calls_count\":2}\n\n",
                        "data: [DONE]\n\n"
                ).subscribeOn(Schedulers.single()));

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

        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString()))
                .thenReturn(Flux.just(
                        "data: {\"content\":\"Hello from pure content\"}\n\n",
                        "data: {\"content\":\" stream\"}\n\n",
                        "data: [DONE]\n\n"
                ).subscribeOn(Schedulers.single()));

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
        Message user = messageMapper.selectOne(Wrappers.<Message>lambdaQuery()
                .eq(Message::getRole, "user")
                .eq(Message::getRequestId, requestId));
        assertNotNull(user, "user message should be persisted");
        assertEquals("hello world", user.getContent());
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
}
