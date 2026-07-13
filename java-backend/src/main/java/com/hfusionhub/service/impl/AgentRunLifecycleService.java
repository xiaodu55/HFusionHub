package com.hfusionhub.service.impl;

import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Agent run 状态机收口：所有受守卫的 run 状态迁移（条件 UPDATE，行级原子判定）
 * 与用量账本结算统一从这里走。
 *
 * <p>背景（REPAIR_ROADMAP S3/M3）：deny / approve / expire / resume 失败收敛四处
 * run 状态迁移此前是 selectById + 内存判断 + updateById 的 check-then-act 写法，
 * 在过期调度与用户决定并发时可能双向覆盖。现统一改为
 * {@code UPDATE ... WHERE status = ...} 条件迁移，竞态由数据库行级判定，
 * 只有真正完成迁移的一方负责结算用量。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentRunLifecycleService {

    private final AgentRunMapper runMapper;
    private final AgentTaskMapper taskMapper;
    private final UserMapper userMapper;
    private final UsageLedgerService usageLedgerService;

    /**
     * 审批拒绝：waiting_approval → failed。
     *
     * @return true 表示本调用完成了迁移（调用方据此结算用量）；false 表示
     * run 已被并发方（如过期调度）迁移过，无需重复处理
     */
    public boolean failFromWaitingApproval(Long runId, String errorCode, String errorDetail) {
        return runMapper.transitionRunStatusGuarded(
                runId,
                AgentConstants.STATUS_WAITING_APPROVAL,
                AgentConstants.STATUS_FAILED,
                errorCode,
                errorDetail,
                LocalDateTime.now()) == 1;
    }

    /**
     * 审批批准：waiting_approval → running。
     *
     * @return true 表示本调用完成了迁移；false 表示 run 已被并发方改变
     */
    public boolean resumeFromWaitingApproval(Long runId) {
        return runMapper.transitionRunStatusGuarded(
                runId,
                AgentConstants.STATUS_WAITING_APPROVAL,
                AgentConstants.STATUS_RUNNING,
                null,
                null,
                null) == 1;
    }

    /**
     * 审批后恢复失败的收敛：任意非终态 → failed（M3，防止覆盖并发写入的真实终态）。
     */
    public boolean failUnlessTerminal(Long runId, String errorCode, String errorDetail) {
        return runMapper.transitionRunStatusFromAnyActive(
                runId,
                AgentConstants.TERMINAL_STATUSES,
                AgentConstants.STATUS_FAILED,
                errorCode,
                errorDetail,
                LocalDateTime.now()) == 1;
    }

    /**
     * 用量账本结算：成功按实际 token 结算，其余状态退回预占
     * （自 AgentTaskServiceImpl.finalizeAgentRunUsage 收口）。
     */
    @Transactional
    public void finalizeAgentRunUsage(Long runId, String status, Map<String, Object> tokenUsage) {
        AgentRun run = runMapper.selectById(runId);
        if (run == null || run.getRunUuid() == null) {
            return;
        }
        Long tenantId = resolveRunTenant(run, null);
        if (tenantId == null) {
            log.warn("Cannot finalize AGENT_TOKENS for run {} — tenant unresolvable", runId);
            return;
        }
        final Long tenant = tenantId;
        final String usageKey = "agent_run:" + run.getRunUuid();
        TenantContext.runAs(tenant, () -> {
            if (AgentConstants.STATUS_SUCCEEDED.equals(status)) {
                long actual = extractTotalTokens(tokenUsage);
                usageLedgerService.settle(
                        UsageMeter.AGENT_TOKENS, usageKey, actual, "agent_run", String.valueOf(runId));
            } else {
                usageLedgerService.release(UsageMeter.AGENT_TOKENS, usageKey);
            }
            return null;
        });
    }

    /**
     * Resolves the durable owner for an Agent run.  AgentTask has no tenant
     * column, so a legacy run without tenant_id must be attributed through its
     * task owner.  Do not use a request/worker thread-local as an authority.
     */
    public Long resolveRunTenant(AgentRun run, AgentTask task) {
        if (run.getTenantId() != null) {
            return run.getTenantId();
        }
        AgentTask resolvedTask = task != null ? task : taskMapper.selectById(run.getTaskId());
        if (resolvedTask == null || resolvedTask.getUserId() == null) {
            return null;
        }
        User owner = userMapper.selectById(resolvedTask.getUserId());
        return owner != null ? owner.getTenantId() : null;
    }

    /**
     * 从 tokenUsage 字典提取实际 total_tokens（缺省 0）。
     */
    private long extractTotalTokens(Map<String, Object> tokenUsage) {
        if (tokenUsage == null) {
            return 0L;
        }
        Object total = tokenUsage.get("total_tokens");
        if (total instanceof Number n) {
            return Math.max(0L, n.longValue());
        }
        Object prompt = tokenUsage.get("prompt_tokens");
        Object completion = tokenUsage.get("completion_tokens");
        long p = prompt instanceof Number pn ? Math.max(0L, pn.longValue()) : 0L;
        long c = completion instanceof Number cn ? Math.max(0L, cn.longValue()) : 0L;
        return p + c;
    }
}
