package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.dto.MessageSendDTO;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.Conversation;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.UsageCounterMapper;
import com.hfusionhub.mapper.UsageEventMapper;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.service.ConversationService;
import com.hfusionhub.service.MemoryService;
import com.hfusionhub.service.UsageLedgerService;
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
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

/**
 * 流式聊天用量结算集成测试（P0-4 异步上下文回归）。
 *
 * <p>验证：流式响应的结算/退回发生在 Reactor 调度线程（无租户上下文），
 * 通过预捕获的 tenant ID + {@code TenantContext.runAs} 恢复后完成，预留不泄漏。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class ConversationStreamingUsageTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @MockBean
    private AiClient aiClient;

    @MockBean
    private AgentTaskService agentTaskService;

    @MockBean
    private MemoryService memoryService;

    @Autowired
    private ConversationService conversationService;

    @Autowired
    private ConversationMapper conversationMapper;

    @Autowired
    private UsageLedgerService usageLedgerService;

    @Autowired
    private UsageEventMapper usageEventMapper;

    @Autowired
    private UsageReservationMapper usageReservationMapper;

    @Autowired
    private UsageCounterMapper usageCounterMapper;

    private Long conversationId;

    @BeforeEach
    void setUp() {
        // 共享 H2 单 JVM 内持久：流式结算在 Reactor 线程单独提交，先清账本保证断言自洽
        usageEventMapper.delete(Wrappers.emptyWrapper());
        usageReservationMapper.delete(Wrappers.emptyWrapper());
        usageCounterMapper.delete(Wrappers.emptyWrapper());
        TenantContext.setTenantId(1L);
        Conversation conversation = new Conversation();
        conversation.setUserId(1L);
        conversation.setTitle("stream-test");
        conversationMapper.insert(conversation);
        conversationId = conversation.getId();

        when(memoryService.getRelevantMemories(any(), any(), any(), anyInt())).thenReturn(List.of());

        AgentTask task = new AgentTask();
        task.setId(1L);
        AgentRun run = new AgentRun();
        run.setId(1L);
        run.setStatus("running");
        when(agentTaskService.createTask(anyString(), anyLong(), anyLong(), any(), anyString())).thenReturn(task);
        when(agentTaskService.startRun(anyLong(), anyString(), any(), anyString(), anyInt())).thenReturn(run);
        when(agentTaskService.getRunById(anyLong())).thenReturn(null);
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void streamingCompletionSettlesUsageOnContextlessReactorThread() {
        // 异步 Flux：在 Schedulers.single 线程上发出 [DONE]，模拟无租户上下文的回调线程
        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString()))
                .thenReturn(Flux.just("data: [DONE]\n\n").subscribeOn(Schedulers.single()));

        MessageSendDTO dto = new MessageSendDTO();
        dto.setConversationId(conversationId);
        dto.setContent("hello world");
        dto.setRequestId("stream-ctx-1");

        conversationService.sendMessageStream(dto, new SseEmitter(), 1L, new AtomicBoolean(false));

        // 输入 "hello world" → 估算 64 token；结算 = min(64+512, 64 + 0) = 64
        long expectedCommitted = 64L;
        long deadline = System.currentTimeMillis() + 8000;
        while (System.currentTimeMillis() < deadline
                && usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS) != expectedCommitted) {
            sleep(50);
        }

        assertEquals(expectedCommitted, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(0L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void streamingErrorReleasesReservationOnContextlessReactorThread() {
        // Flux 立即报错：onError 在调度线程执行，必须 runAs 恢复上下文后 RELEASE
        when(aiClient.streamChat(anyString(), anyLong(), any(), any(), anyString()))
                .thenReturn(Flux.<String>error(new RuntimeException("simulated stream failure"))
                        .subscribeOn(Schedulers.single()));

        MessageSendDTO dto = new MessageSendDTO();
        dto.setConversationId(conversationId);
        dto.setContent("boom");
        dto.setRequestId("stream-ctx-2");

        conversationService.sendMessageStream(dto, new SseEmitter(), 1L, new AtomicBoolean(false));

        long deadline = System.currentTimeMillis() + 8000;
        while (System.currentTimeMillis() < deadline
                && usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS) != 0L) {
            sleep(50);
        }

        // 输入 "boom" → 估算 64；预占 64+512=576，出错后全部退回
        assertEquals(0L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(0L, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
    }

    private void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
