package com.hfusionhub.bot;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.service.OpenApiService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 机器人回答服务 — 把平台消息桥接到开放 API 对话链路（Batch 6）。
 *
 * <p>复用 {@link OpenApiService#chat} 的完整鉴权/限流/计费/审计语义：
 * 机器人的 appKey 即某个已发布应用的 API Key，应用绑定的知识库决定回答范围。
 * 任何失败都降级为用户可读的兜底文案，绝不把内部异常文本抛给 IM 用户。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BotChatService {

    static final String MISCONFIGURED_REPLY = "机器人尚未配置回答服务，请联系管理员。";
    static final String ERROR_REPLY = "抱歉，回答服务暂时不可用，请稍后重试。";

    private final OpenApiService openApiService;

    /**
     * 回答一条 IM 消息。
     *
     * @param appKey   机器人绑定的开放 API Key（空 = 未配置）
     * @param senderId 发送者标识（用于日志与审计关联）
     * @param text     用户消息文本
     * @return 回复文本（永不返回 null）
     */
    public String answer(String appKey, String senderId, String text) {
        if (appKey == null || appKey.isBlank()) {
            log.warn("Bot appKey not configured; sender={}", senderId);
            return MISCONFIGURED_REPLY;
        }
        String query = text == null ? "" : text.strip();
        if (query.isEmpty()) {
            return ERROR_REPLY;
        }
        if (query.length() > 4000) {
            query = query.substring(0, 4000);
        }
        OpenApiChatRequest request = new OpenApiChatRequest();
        request.setQuery(query);
        try {
            OpenApiChatResponse response = openApiService.chat(appKey, request);
            String content = response == null ? null : response.getContent();
            return content == null || content.isBlank() ? ERROR_REPLY : content;
        } catch (BusinessException e) {
            log.warn("Bot open-api call rejected: sender={}, code={}, msg={}",
                    senderId, e.getCode(), e.getMessage());
            return "调用受限：" + e.getMessage();
        } catch (Exception e) {
            log.warn("Bot open-api call failed: sender={}, err={}", senderId, e.getMessage());
            return ERROR_REPLY;
        }
    }
}
