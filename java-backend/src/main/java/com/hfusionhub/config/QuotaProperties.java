package com.hfusionhub.config;

import lombok.Getter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 租户配额默认值（按 plan_tier 分档）
 *
 * <p>与 application.yml 的 {@code hfusionhub.quota.defaults.{free|pro|enterprise}.{meter}} 对应。
 * 某租户未配置 {@code tenant_quota} 覆盖时，服务层按本配置回落。</p>
 *
 * @author HFusionHub Team
 */
@Getter
@Component
public class QuotaProperties {

    @Value("${hfusionhub.quota.chat.max-output-tokens:8192}")
    private long chatMaxOutputTokens;

    @Value("${hfusionhub.quota.defaults.free.chat-tokens:100000}")
    private long freeChatTokens;

    @Value("${hfusionhub.quota.defaults.free.agent-tokens:100000}")
    private long freeAgentTokens;

    @Value("${hfusionhub.quota.defaults.free.index-chunks:5000}")
    private long freeIndexChunks;

    @Value("${hfusionhub.quota.defaults.free.plugin-executions:100}")
    private long freePluginExecutions;

    @Value("${hfusionhub.quota.defaults.pro.chat-tokens:1000000}")
    private long proChatTokens;

    @Value("${hfusionhub.quota.defaults.pro.agent-tokens:1000000}")
    private long proAgentTokens;

    @Value("${hfusionhub.quota.defaults.pro.index-chunks:50000}")
    private long proIndexChunks;

    @Value("${hfusionhub.quota.defaults.pro.plugin-executions:1000}")
    private long proPluginExecutions;

    @Value("${hfusionhub.quota.defaults.enterprise.chat-tokens:10000000}")
    private long enterpriseChatTokens;

    @Value("${hfusionhub.quota.defaults.enterprise.agent-tokens:10000000}")
    private long enterpriseAgentTokens;

    @Value("${hfusionhub.quota.defaults.enterprise.index-chunks:500000}")
    private long enterpriseIndexChunks;

    @Value("${hfusionhub.quota.defaults.enterprise.plugin-executions:10000}")
    private long enterprisePluginExecutions;

    /**
     * 按 plan_tier + 计量项取默认日限额。
     *
     * @param planTier free|pro|enterprise（其他值按 free 处理）
     * @param meter    计量项
     * @return 日限额
     */
    public long defaultLimit(String planTier, String meterCode) {
        switch (meterCode) {
            case "chat_tokens":
                switch (planTier) {
                    case "pro":
                        return proChatTokens;
                    case "enterprise":
                        return enterpriseChatTokens;
                    default:
                        return freeChatTokens;
                }
            case "agent_tokens":
                switch (planTier) {
                    case "pro":
                        return proAgentTokens;
                    case "enterprise":
                        return enterpriseAgentTokens;
                    default:
                        return freeAgentTokens;
                }
            case "index_chunks":
                switch (planTier) {
                    case "pro":
                        return proIndexChunks;
                    case "enterprise":
                        return enterpriseIndexChunks;
                    default:
                        return freeIndexChunks;
                }
            case "plugin_executions":
                switch (planTier) {
                    case "pro":
                        return proPluginExecutions;
                    case "enterprise":
                        return enterprisePluginExecutions;
                    default:
                        return freePluginExecutions;
                }
            default:
                return freeChatTokens;
        }
    }
}
