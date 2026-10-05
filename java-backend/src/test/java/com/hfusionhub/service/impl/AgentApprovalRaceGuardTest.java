package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.config.QuotaProperties;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskQueueService;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.UsageLedgerService;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

/**
 * 审批竞态守卫回归测试（REPAIR_ROADMAP S3/M3）。
 *
 * <p>验证 deny / approve / expire / resume 失败收敛四条路径：
 * 状态迁移统一走 {@link AgentRunLifecycleService} 的条件 UPDATE，
 * 且只有真正完成迁移的一方结算用量账本。</p>
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AgentApprovalRaceGuardTest {

    private static final Long TASK_ID = 2L;
    private static final Long RUN_ID = 3L;
    private static final Long DECIDER_ID = 9L;

    @Mock
    private AgentTaskMapper taskMapper;

    @Mock
    private AgentRunMapper runMapper;

    @Mock
    private AgentStepMapper stepMapper;

    @Mock
    private AgentApprovalMapper approvalMapper;

    @Mock
    private MessageMapper messageMapper;

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
    private AgentTaskDecisionService decisionService;

    @BeforeEach
    void setUp() {
        service = new AgentTaskServiceImpl(
                taskMapper,
                runMapper,
                stepMapper,
                approvalMapper,
                userMapper,
                aiClient,
                queueService,
                statusEventService,
                redisUtils,
                usageLedgerService,
                quotaProperties,
                costTrackingService,
                runLifecycle);
        // 拆分后 decideApproval 归属 AgentTaskDecisionService（同第二十四批）；
        // agentTaskService 传真实 impl，recordStep 走 impl 的 stepMapper mock
        decisionService = new AgentTaskDecisionService(
                stepMapper,
                approvalMapper,
                taskMapper,
                runMapper,
                runLifecycle,
                statusEventService,
                aiClient,
                messageMapper,
                service);
    }

    private AgentApproval pendingApproval() {
        AgentApproval approval = new AgentApproval();
        approval.setId(1L);
        approval.setTaskId(TASK_ID);
        approval.setRunId(RUN_ID);
        approval.setStatus("pending");
        approval.setExpiresAt(LocalDateTime.now().plusMinutes(5));
        approval.setToolName("calculator");
        return approval;
    }

    private AgentTask waitingTask() {
        AgentTask task = new AgentTask();
        task.setId(TASK_ID);
        task.setStatus(AgentConstants.STATUS_WAITING_APPROVAL);
        return task;
    }

    private AgentRun waitingRun() {
        AgentRun run = new AgentRun();
        run.setId(RUN_ID);
        run.setStatus(AgentConstants.STATUS_WAITING_APPROVAL);
        return run;
    }

    private void stubApprovalFlow(String decision) {
        when(approvalMapper.selectByApprovalId("appr-1")).thenReturn(pendingApproval());
        when(approvalMapper.updateDecision(eq(1L), eq(decision), any(), anyString(), any()))
                .thenReturn(1);
        when(taskMapper.selectById(TASK_ID)).thenReturn(waitingTask());
        when(runMapper.selectById(RUN_ID)).thenReturn(waitingRun());
    }

    @Test
    void denySettlesUsageOnlyWhenGuardedTransitionWins() {
        stubApprovalFlow("denied");
        when(runLifecycle.failFromWaitingApproval(eq(RUN_ID), eq("approval_denied"), anyString()))
                .thenReturn(true);

        decisionService.decideApproval("appr-1", "denied", DECIDER_ID, "不要执行");

        verify(runLifecycle).failFromWaitingApproval(eq(RUN_ID), eq("approval_denied"), anyString());
        verify(runLifecycle).finalizeAgentRunUsage(RUN_ID, AgentConstants.STATUS_FAILED, null);
    }

    @Test
    void denySkipsUsageSettlementWhenConcurrentMigrationAlreadyWon() {
        stubApprovalFlow("denied");
        // 过期调度已把 run 迁移为终态（条件 UPDATE 命中 0 行）
        when(runLifecycle.failFromWaitingApproval(eq(RUN_ID), eq("approval_denied"), anyString()))
                .thenReturn(false);

        decisionService.decideApproval("appr-1", "denied", DECIDER_ID, "不要执行");

        verify(runLifecycle).failFromWaitingApproval(eq(RUN_ID), eq("approval_denied"), anyString());
        verify(runLifecycle, never()).finalizeAgentRunUsage(anyLong(), anyString(), any());
    }

    @Test
    void approveResumesRunViaGuardedTransition() {
        stubApprovalFlow("approved");
        when(approvalMapper.issueExecutionToken(eq(1L), anyString(), anyString(), anyString()))
                .thenReturn(1);
        when(runLifecycle.resumeFromWaitingApproval(RUN_ID)).thenReturn(true);
        when(aiClient.decideApproval(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenThrow(new RuntimeException("python down"));
        // 恢复失败后的收敛：重读 run 仍非终态 → 条件迁移成功
        when(runMapper.selectById(RUN_ID)).thenReturn(waitingRun());
        when(runLifecycle.failUnlessTerminal(eq(RUN_ID), eq("internal_error"), anyString()))
                .thenReturn(true);

        decisionService.decideApproval("appr-1", "approved", DECIDER_ID, null);

        verify(runLifecycle).resumeFromWaitingApproval(RUN_ID);
        // M3：恢复失败必须把 run 收敛为 failed，并结算用量
        verify(runLifecycle).failUnlessTerminal(eq(RUN_ID), eq("internal_error"), anyString());
        verify(runLifecycle).finalizeAgentRunUsage(RUN_ID, AgentConstants.STATUS_FAILED, null);
    }

    @Test
    void approveDoesNotOverwriteTerminalWhenConvergenceLoses() {
        stubApprovalFlow("approved");
        when(approvalMapper.issueExecutionToken(eq(1L), anyString(), anyString(), anyString()))
                .thenReturn(1);
        when(runLifecycle.resumeFromWaitingApproval(RUN_ID)).thenReturn(true);
        when(aiClient.decideApproval(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenThrow(new RuntimeException("python down"));
        when(runMapper.selectById(RUN_ID)).thenReturn(waitingRun());
        // run 在恢复期间真实完成（SUCCEEDED）→ 条件迁移命中 0 行，绝不覆盖终态
        when(runLifecycle.failUnlessTerminal(eq(RUN_ID), eq("internal_error"), anyString()))
                .thenReturn(false);

        decisionService.decideApproval("appr-1", "approved", DECIDER_ID, null);

        verify(runLifecycle, never()).finalizeAgentRunUsage(RUN_ID, AgentConstants.STATUS_FAILED, null);
    }

    @Test
    void approveFailsClosedWhenTokenIssuanceReturnsZero() {
        stubApprovalFlow("approved");
        // 第五十四批：签发命中 0 行（审批不在可签发状态）必须整体失败——
        // 事务回滚使 approval 回到 pending，绝不带着 null token 调 Python resume
        when(approvalMapper.issueExecutionToken(eq(1L), anyString(), anyString(), anyString()))
                .thenReturn(0);

        assertThatThrownBy(() -> decisionService.decideApproval("appr-1", "approved", DECIDER_ID, null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("执行令牌签发失败");

        verify(aiClient, never())
                .decideApproval(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any());
        verify(runLifecycle, never()).resumeFromWaitingApproval(anyLong());
    }

    @Test
    void approveFailsClosedWhenTokenIssuanceThrows() {
        stubApprovalFlow("approved");
        // 签发 SQL 异常同样 fail-closed：抛出 → 事务回滚，而不是吞掉后以
        // null token 继续（旧版行为，第五十四批移除）
        when(approvalMapper.issueExecutionToken(eq(1L), anyString(), anyString(), anyString()))
                .thenThrow(new RuntimeException("db down"));

        assertThatThrownBy(() -> decisionService.decideApproval("appr-1", "approved", DECIDER_ID, null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("执行令牌签发失败");

        verify(aiClient, never())
                .decideApproval(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any());
        verify(runLifecycle, never()).resumeFromWaitingApproval(anyLong());
    }

    @Test
    void approveSkipsTaskOverwriteWhenGuardedTransitionLoses() {
        stubApprovalFlow("approved");
        when(approvalMapper.issueExecutionToken(eq(1L), anyString(), anyString(), anyString()))
                .thenReturn(1);
        when(runLifecycle.resumeFromWaitingApproval(RUN_ID)).thenReturn(true);
        // task 条件迁移命中 0 行（并发已迁移/终态）→ 不再退回 updateById 覆盖
        when(taskMapper.transitionTaskGuarded(eq(TASK_ID), anyString(), any())).thenReturn(0);
        when(aiClient.decideApproval(
                        any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(), any(),
                        any()))
                .thenThrow(new RuntimeException("python down"));
        when(runMapper.selectById(RUN_ID)).thenReturn(waitingRun());
        when(runLifecycle.failUnlessTerminal(eq(RUN_ID), eq("internal_error"), anyString()))
                .thenReturn(true);

        decisionService.decideApproval("appr-1", "approved", DECIDER_ID, null);

        // 第五十四批：decideApproval 全链路的 task 写入只走条件守卫，
        // 任何路径都不再出现无条件 updateById 覆盖
        verify(taskMapper, never()).updateById(any(AgentTask.class));
    }

    @Test
    void expireSettlesUsageOnlyWhenGuardedTransitionWins() {
        AgentApproval expired = pendingApproval();
        when(approvalMapper.selectExpiredPending()).thenReturn(List.of(expired));
        when(approvalMapper.updateDecision(eq(1L), eq("expired"), any(), anyString(), anyString()))
                .thenReturn(1);
        when(taskMapper.selectBatchIds(any())).thenReturn(List.of());
        when(runMapper.selectBatchIds(any())).thenReturn(List.of(waitingRun()));
        when(runLifecycle.failFromWaitingApproval(eq(RUN_ID), eq(AgentConstants.ERR_APPROVAL_EXPIRED), anyString()))
                .thenReturn(true);

        int count = service.expireApprovals();

        assertThat(count).isEqualTo(1);
        verify(runLifecycle)
                .failFromWaitingApproval(eq(RUN_ID), eq(AgentConstants.ERR_APPROVAL_EXPIRED), contains("审批超时"));
        verify(runLifecycle).finalizeAgentRunUsage(RUN_ID, AgentConstants.STATUS_FAILED, null);
    }

    @Test
    void expireSkipsUsageSettlementWhenRunAlreadyResumed() {
        AgentApproval expired = pendingApproval();
        when(approvalMapper.selectExpiredPending()).thenReturn(List.of(expired));
        when(approvalMapper.updateDecision(eq(1L), eq("expired"), any(), anyString(), anyString()))
                .thenReturn(1);
        when(taskMapper.selectBatchIds(any())).thenReturn(List.of());
        when(runMapper.selectBatchIds(any())).thenReturn(List.of(waitingRun()));
        // 用户刚批准（run 已 RUNNING）→ 条件迁移命中 0 行，不得覆盖
        when(runLifecycle.failFromWaitingApproval(eq(RUN_ID), eq(AgentConstants.ERR_APPROVAL_EXPIRED), anyString()))
                .thenReturn(false);

        int count = service.expireApprovals();

        assertThat(count).isEqualTo(1);
        verify(runLifecycle, never()).finalizeAgentRunUsage(anyLong(), anyString(), any());
    }
}
