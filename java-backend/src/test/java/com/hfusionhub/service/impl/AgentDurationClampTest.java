package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.config.QuotaProperties;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskQueueService;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.UsageLedgerService;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

/**
 * 负耗时钳制回归测试（质量门禁 R4 的源头修复：负 latency_ms 曾由
 * 墙钟回拨经 completeRun fallback / 审批恢复路径写入 model_usage_record）。
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AgentDurationClampTest {

    private static final Long TASK_ID = 2L;
    private static final Long RUN_ID = 3L;

    @Mock
    private AgentTaskMapper taskMapper;
    @Mock
    private AgentRunMapper runMapper;
    @Mock
    private AgentStepMapper stepMapper;
    @Mock
    private AgentApprovalMapper approvalMapper;
    @Mock
    private UserMapper userMapper;
    @Mock
    private AiClient aiClient;
    @Mock
    private AgentTaskQueueService queueService;
    @Mock
    private AgentStatusEventService statusEventService;
    @Mock
    private RedisUtils redisUtils;
    @Mock
    private UsageLedgerService usageLedgerService;
    @Mock
    private QuotaProperties quotaProperties;
    @Mock
    private CostTrackingService costTrackingService;
    @Mock
    private AgentRunLifecycleService runLifecycle;

    private AgentTaskServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new AgentTaskServiceImpl(
                taskMapper, runMapper, stepMapper, approvalMapper,
                userMapper, aiClient, queueService, statusEventService, redisUtils,
                usageLedgerService, quotaProperties, costTrackingService, runLifecycle);
    }

    private AgentRun runningRun(LocalDateTime startedAt) {
        AgentRun run = new AgentRun();
        run.setId(RUN_ID);
        run.setTaskId(TASK_ID);
        run.setStatus(AgentConstants.STATUS_RUNNING);
        run.setStartedAt(startedAt);
        return run;
    }

    private AgentTask owningTask() {
        AgentTask task = new AgentTask();
        task.setId(TASK_ID);
        task.setStatus(AgentConstants.STATUS_RUNNING);
        task.setCurrentRunId(RUN_ID);
        return task;
    }

    @Test
    void completeRunClampsNegativeFallbackDurationFromClockRollback() {
        // 模拟时钟回拨：startedAt 在"当前"之后 10 分钟 → 相减为负，必须钳为 0
        when(runMapper.selectById(RUN_ID))
                .thenReturn(runningRun(LocalDateTime.now().plusMinutes(10)));
        when(runMapper.completeRunGuarded(
                eq(RUN_ID), anyString(), isNull(), isNull(), isNull(), any()))
                .thenReturn(1);
        when(taskMapper.selectById(TASK_ID)).thenReturn(owningTask());

        service.completeRun(RUN_ID, AgentConstants.STATUS_SUCCEEDED,
                null, null, 0, 0L, null, null, null);

        ArgumentCaptor<Long> duration = ArgumentCaptor.forClass(Long.class);
        org.mockito.Mockito.verify(runMapper).updateCompletionMetadata(
                eq(RUN_ID), isNull(), isNull(), any(), duration.capture());
        assertThat(duration.getValue()).isZero();
    }

    @Test
    void completeRunKeepsPositiveCallerProvidedDuration() {
        when(runMapper.selectById(RUN_ID))
                .thenReturn(runningRun(LocalDateTime.now().minusSeconds(30)));
        when(runMapper.completeRunGuarded(
                eq(RUN_ID), anyString(), isNull(), isNull(), isNull(), any()))
                .thenReturn(1);
        when(taskMapper.selectById(TASK_ID)).thenReturn(owningTask());

        service.completeRun(RUN_ID, AgentConstants.STATUS_SUCCEEDED,
                null, null, 0, 5000L, null, null, null);

        ArgumentCaptor<Long> duration = ArgumentCaptor.forClass(Long.class);
        org.mockito.Mockito.verify(runMapper).updateCompletionMetadata(
                eq(RUN_ID), isNull(), isNull(), any(), duration.capture());
        assertThat(duration.getValue()).isEqualTo(5000L);
    }

    @Test
    void clampKeepsPositiveCallerProvidedDuration() {
        LocalDateTime past = LocalDateTime.now().minusSeconds(30);
        assertThat(AgentTaskSupport.clampDuration(5000L, past)).isEqualTo(5000L);
        assertThat(AgentTaskSupport.clampDuration(5000L, null)).isEqualTo(5000L);
    }

    @Test
    void clampReturnsZeroWhenCallerPassesNegativeAndNoStartedAt() {
        assertThat(AgentTaskSupport.clampDuration(-5L, null)).isZero();
    }

    @Test
    void clampReturnsZeroOnClockRollback() {
        // 时钟回拨：startedAt 晚于当前墙钟 → 相减为负 → 钳为 0
        LocalDateTime future = LocalDateTime.now().plusMinutes(10);
        assertThat(AgentTaskSupport.clampDuration(0L, future)).isZero();
        assertThat(AgentTaskSupport.clampDuration(-5L, future)).isZero();
    }

    @Test
    void clampFallbackFromStartedAtIsNonNegative() {
        LocalDateTime past = LocalDateTime.now().minusSeconds(30);
        assertThat(AgentTaskSupport.clampDuration(0L, past)).isGreaterThanOrEqualTo(0L);
    }
}
