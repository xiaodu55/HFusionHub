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

    @Value("${hfusionhub.quota.defaults.free.bid-projects:10}")
    private long freeBidProjects;

    @Value("${hfusionhub.quota.defaults.free.tender-elements:500}")
    private long freeTenderElements;

    @Value("${hfusionhub.quota.defaults.free.bid-draft-chars:100000}")
    private long freeBidDraftChars;

    @Value("${hfusionhub.quota.defaults.free.bid-check-reports:50}")
    private long freeBidCheckReports;

    @Value("${hfusionhub.quota.defaults.pro.chat-tokens:1000000}")
    private long proChatTokens;

    @Value("${hfusionhub.quota.defaults.pro.agent-tokens:1000000}")
    private long proAgentTokens;

    @Value("${hfusionhub.quota.defaults.pro.index-chunks:50000}")
    private long proIndexChunks;

    @Value("${hfusionhub.quota.defaults.pro.plugin-executions:1000}")
    private long proPluginExecutions;

    @Value("${hfusionhub.quota.defaults.pro.bid-projects:100}")
    private long proBidProjects;

    @Value("${hfusionhub.quota.defaults.pro.tender-elements:5000}")
    private long proTenderElements;

    @Value("${hfusionhub.quota.defaults.pro.bid-draft-chars:1000000}")
    private long proBidDraftChars;

    @Value("${hfusionhub.quota.defaults.pro.bid-check-reports:500}")
    private long proBidCheckReports;

    @Value("${hfusionhub.quota.defaults.enterprise.chat-tokens:10000000}")
    private long enterpriseChatTokens;

    @Value("${hfusionhub.quota.defaults.enterprise.agent-tokens:10000000}")
    private long enterpriseAgentTokens;

    @Value("${hfusionhub.quota.defaults.enterprise.index-chunks:500000}")
    private long enterpriseIndexChunks;

    @Value("${hfusionhub.quota.defaults.enterprise.plugin-executions:10000}")
    private long enterprisePluginExecutions;

    @Value("${hfusionhub.quota.defaults.enterprise.bid-projects:1000}")
    private long enterpriseBidProjects;

    @Value("${hfusionhub.quota.defaults.enterprise.tender-elements:50000}")
    private long enterpriseTenderElements;

    @Value("${hfusionhub.quota.defaults.enterprise.bid-draft-chars:10000000}")
    private long enterpriseBidDraftChars;

    @Value("${hfusionhub.quota.defaults.enterprise.bid-check-reports:5000}")
    private long enterpriseBidCheckReports;

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
            case "bid_projects":
                switch (planTier) {
                    case "pro":
                        return proBidProjects;
                    case "enterprise":
                        return enterpriseBidProjects;
                    default:
                        return freeBidProjects;
                }
            case "tender_elements":
                switch (planTier) {
                    case "pro":
                        return proTenderElements;
                    case "enterprise":
                        return enterpriseTenderElements;
                    default:
                        return freeTenderElements;
                }
            case "bid_draft_chars":
                switch (planTier) {
                    case "pro":
                        return proBidDraftChars;
                    case "enterprise":
                        return enterpriseBidDraftChars;
                    default:
                        return freeBidDraftChars;
                }
            case "bid_check_reports":
                switch (planTier) {
                    case "pro":
                        return proBidCheckReports;
                    case "enterprise":
                        return enterpriseBidCheckReports;
                    default:
                        return freeBidCheckReports;
                }
            default:
                return freeChatTokens;
        }
    }
}
