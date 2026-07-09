package com.hfusionhub.bot;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * IM 机器人适配器配置（Batch 6 发布渠道）。
 *
 * <p>所有机器人默认关闭；每个机器人通过 {@code appKey} 复用开放 API 的
 * 应用鉴权/限流/计费链路（app_api_key → 已发布应用 → 绑定知识库）。</p>
 *
 * <pre>
 * bots:
 *   dingtalk:
 *     enabled: true
 *     app-key: &lt;开放 API Key&gt;      # 回答走 /openapi/chat 同源鉴权
 *     app-secret: &lt;钉钉加签密钥&gt;    # 回调签名校验（企业内部机器人 HTTP 模式）
 *   feishu:
 *     enabled: true
 *     app-key: &lt;开放 API Key&gt;
 *     app-id / app-secret:         # tenant_access_token 获取
 *     verification-token:          # 事件订阅令牌校验（明文模式）
 *   wecom:
 *     enabled: true
 *     app-key: &lt;开放 API Key&gt;
 *     corp-id / corp-secret / agent-id / token / encoding-aes-key
 * </pre>
 */
@Data
@Component
@ConfigurationProperties(prefix = "bots")
public class BotProperties {

    private DingTalk dingtalk = new DingTalk();
    private Feishu feishu = new Feishu();
    private WeCom wecom = new WeCom();

    @Data
    public static class DingTalk {
        private boolean enabled = false;
        /** 开放 API Key —— 机器人回答走 /openapi/chat 同一套鉴权与计费 */
        private String appKey = "";
        /** 回调签名密钥（企业内部机器人 HTTP 回调模式的加签 secret） */
        private String appSecret = "";
    }

    @Data
    public static class Feishu {
        private boolean enabled = false;
        private String appKey = "";
        /** 飞书自建应用凭证（tenant_access_token） */
        private String appId = "";
        private String appSecret = "";
        /** 事件订阅 verification token（明文模式；未配置则跳过校验） */
        private String verificationToken = "";
    }

    @Data
    public static class WeCom {
        private boolean enabled = false;
        private String appKey = "";
        /** 企业微信凭证 */
        private String corpId = "";
        private String corpSecret = "";
        private Integer agentId = 0;
        /** 回调验签 Token 与消息加解密 EncodingAESKey（43 位 Base64） */
        private String token = "";
        private String encodingAesKey = "";
    }
}
