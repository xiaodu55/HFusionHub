package com.hfusionhub.quota;

/**
 * 用量计量项
 *
 * @author HFusionHub Team
 */
public enum UsageMeter {

    /** 聊天 token 消耗 */
    CHAT_TOKENS("chat_tokens"),

    /** Agent 运行 token 消耗 */
    AGENT_TOKENS("agent_tokens"),

    /** 文档索引进度（按分块数计量） */
    INDEX_CHUNKS("index_chunks"),

    /** 容器插件执行次数 */
    PLUGIN_EXECUTIONS("plugin_executions"),

    /** 投标项目创建数（招投标垂直化） */
    BID_PROJECTS("bid_projects"),

    /** 招标解读产出要素/需求项数（招投标垂直化） */
    TENDER_ELEMENTS("tender_elements");

    private final String code;

    UsageMeter(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
