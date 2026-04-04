package com.hfusionhub.service;

import com.hfusionhub.quota.UsageMeter;

/**
 * 用量账本服务 — 幂等预占 / 结算 / 退回 + 配额解析。
 *
 * <p>所有方法都以当前线程 {@link com.hfusionhub.tenant.TenantContext} 中的租户为准，
 * 无租户上下文时抛 {@link IllegalStateException}（fail-closed）。</p>
 *
 * @author HFusionHub Team
 */
public interface UsageLedgerService {

    /**
     * 预占用量。同一 requestId 重复调用幂等（只预占一次）。
     * 超限抛 {@link com.hfusionhub.common.exception.BusinessException}（QUOTA_EXCEEDED）。
     *
     * @param meter    计量项
     * @param requestId 业务幂等键（建议格式 {@code <meter>:<业务请求ID>}）
     * @param amount    预占量（&lt;=0 时直接忽略）
     * @param refType   引用类型（message|document_index|agent_run|plugin_execution）
     * @param refId     引用 ID
     */
    void reserve(UsageMeter meter, String requestId, long amount, String refType, String refId);

    /**
     * 结算预占为实际用量。同一 requestId 重复调用幂等。
     *
     * @param meter        计量项
     * @param requestId    业务幂等键
     * @param actualAmount 实际消耗量
     * @param refType      引用类型
     * @param refId        引用 ID
     */
    void settle(UsageMeter meter, String requestId, long actualAmount, String refType, String refId);

    /**
     * 退回预占（失败 / 取消 / 超时）。同一 requestId 重复调用幂等。
     *
     * @param meter     计量项
     * @param requestId 业务幂等键
     */
    void release(UsageMeter meter, String requestId);

    /**
     * 当前租户今日已结算量。
     */
    long currentCommitted(UsageMeter meter);

    /**
     * 当前租户今日已预占未结算量。
     */
    long currentReserved(UsageMeter meter);

    /**
     * 当前租户今日用量（committed + reserved）。
     */
    long currentUsage(UsageMeter meter);

    /**
     * 当前租户某计量项的有效日限额：tenant_quota 覆盖优先，否则回落 plan_tier 默认值。
     */
    long effectiveDailyLimit(UsageMeter meter);

    /**
     * 指定租户某计量项的有效日限额（供管理员/跨租户场景）。
     */
    long effectiveDailyLimit(Long tenantId, UsageMeter meter);
}
