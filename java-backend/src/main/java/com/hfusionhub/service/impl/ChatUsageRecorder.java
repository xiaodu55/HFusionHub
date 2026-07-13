package com.hfusionhub.service.impl;

import com.hfusionhub.entity.Conversation;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 聊天用量记账（自 ConversationServiceImpl 收口）——
 * 账本结算/退回（usage_ledger）与模型用量落账（model_usage_record）统一入口。
 *
 * <p>所有记账方法内部吞异常：账本失败不允许影响聊天主流程（SSE/同步路径）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatUsageRecorder {

    private final ConversationMapper conversationMapper;
    private final CostTrackingService costTrackingService;
    private final UsageLedgerService usageLedgerService;

    /**
     * 聊天 token 预占估算：按内容长度粗估，至少 64 token。
     */
    public long estimateChatTokens(String content) {
        int length = content == null ? 0 : content.length();
        return Math.max(64, length / 4);
    }

    /**
     * 结算/退回流式聊天的用量，AtomicBoolean 保证只执行一次。
     * 在 Reactor 线程调用，需以预捕获的租户 ID 恢复 TenantContext。
     * 结算量 = min(预占上界, 输入估算 + 实际输出/4)，封顶在预留内。
     * 内部吞异常，避免账本失败影响 SSE 主流程。
     */
    public void finalizeChatUsage(
            Long tenantId,
            String usageKey,
            long reserveTokens,
            long inputEstimate,
            AtomicBoolean usageFinalized,
            boolean success,
            int outputChars) {
        if (usageFinalized.compareAndSet(false, true)) {
            TenantContext.runAs(tenantId, () -> {
                try {
                    if (success) {
                        long charge = Math.min(reserveTokens, inputEstimate + Math.max(0, outputChars) / 4);
                        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, usageKey, charge, "message", usageKey);
                    } else {
                        usageLedgerService.release(UsageMeter.CHAT_TOKENS, usageKey);
                    }
                } catch (Exception e) {
                    log.warn("Failed to finalize chat usage for {}: {}", usageKey, e.getMessage());
                }
                return null;
            });
        }
    }

    /**
     * 流式路径的用量落账（model_usage_record，估算值）。
     * 知识库会话由 Agent run 终态记录真实用量，此处跳过避免重复。
     */
    public void recordStreamUsageEstimate(Long conversationId, String content) {
        try {
            if (conversationId == null) {
                return;
            }
            Conversation conv = conversationMapper.selectById(conversationId);
            if (conv == null || conv.getUserId() == null) {
                return;
            }
            // 知识库会话由 Agent run 终态记录真实用量，此处跳过避免重复。
            if (conv.getKnowledgeBaseId() != null && conv.getKnowledgeBaseId() > 0) {
                return;
            }
            ModelUsageRecord rec = new ModelUsageRecord();
            rec.setUserId(conv.getUserId());
            rec.setTenantId(TenantContext.getTenantId());
            rec.setConversationId(conversationId);
            rec.setModel("streaming");
            rec.setProvider("streaming");
            rec.setRequestType("chat");
            int outTokens = content == null ? 0 : Math.max(1, content.length() / 4);
            rec.setPromptTokens(0);
            rec.setCompletionTokens(outTokens);
            rec.setTotalTokens(outTokens);
            rec.setCostUsd(BigDecimal.ZERO);
            rec.setLatencyMs(0);
            costTrackingService.record(rec);
            log.debug("Stream usage estimate recorded: conversationId={} tokens={}", conversationId, outTokens);
        } catch (Exception e) {
            log.warn("Failed to record stream usage estimate (non-blocking): {}", e.getMessage());
        }
    }

    /**
     * 同步聊天路径的模型用量落账（model_usage_record）。
     */
    public void recordChatModelUsage(Long userId, Long conversationId, com.hfusionhub.client.AiClient.ChatResponse aiResponse) {
        try {
            if (userId == null || userId <= 0) {
                return;
            }
            ModelUsageRecord rec = new ModelUsageRecord();
            rec.setUserId(userId);
            rec.setConversationId(conversationId);
            rec.setTenantId(TenantContext.getTenantId());
            String model = aiResponse.getModel();
            rec.setModel(model != null && !model.isBlank() ? model : "unknown");
            rec.setProvider(rec.getModel());
            rec.setRequestType("chat");
            int prompt = 0;
            int completion = 0;
            int total = aiResponse.getTokenCount();
            Map<String, Object> usage = aiResponse.getTokenUsage();
            if (usage != null) {
                prompt = usageInt(usage.get("prompt_tokens"));
                completion = usageInt(usage.get("completion_tokens"));
                total = usageInt(usage.get("total_tokens"));
                if (total <= 0) {
                    total = prompt + completion;
                }
            }
            rec.setPromptTokens(prompt);
            rec.setCompletionTokens(completion);
            rec.setTotalTokens(total);
            rec.setCostUsd(BigDecimal.ZERO);
            rec.setLatencyMs(0);
            costTrackingService.record(rec);
            log.debug("Chat model usage recorded: userId={} model={} tokens={}", userId, rec.getModel(), total);
        } catch (Exception e) {
            log.warn("Failed to record chat model usage (non-blocking): {}", e.getMessage());
        }
    }

    private static int usageInt(Object value) {
        return value instanceof Number n ? n.intValue() : 0;
    }
}
