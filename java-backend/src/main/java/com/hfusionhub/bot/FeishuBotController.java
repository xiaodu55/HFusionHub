package com.hfusionhub.bot;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 飞书机器人回调（Batch 6，事件订阅明文模式，默认关闭）。
 *
 * <p>处理两类请求：
 * <ul>
 *   <li>{@code url_verification} —— 回显 challenge 完成订阅地址校验；</li>
 *   <li>{@code im.message.receive_v1} —— 文本消息经 {@link BotChatService}
 *       生成回答，通过飞书 IM API（tenant_access_token + 发送消息）回发到会话。</li>
 * </ul>
 * 校验：header.token 与配置的 verificationToken 常量时间比较（未配置则跳过）。
 * 加密模式（encrypt_key）暂不支持，生产建议开启明文模式并配合内网部署。
 */
@Slf4j
@RestController
@RequestMapping("/openapi/bots/feishu")
@RequiredArgsConstructor
public class FeishuBotController {

    private static final String TOKEN_URL =
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal";
    private static final String MESSAGE_URL =
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id";

    private final BotProperties properties;
    private final BotChatService botChatService;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** tenant_access_token 进程内缓存：key = appId */
    private final Map<String, CachedToken> tokenCache = new ConcurrentHashMap<>();

    @PostMapping
    public Map<String, Object> onEvent(@RequestBody String body) {
        BotProperties.Feishu cfg = properties.getFeishu();
        if (!cfg.isEnabled()) {
            return Map.of("status", "disabled");
        }
        try {
            JsonNode payload = objectMapper.readTree(body);

            // 订阅地址校验：原样回传 challenge
            if ("url_verification".equals(payload.path("type").asText(""))) {
                return Map.of("challenge", payload.path("challenge").asText(""));
            }

            if (!verifyToken(cfg, payload)) {
                log.warn("Feishu bot callback token rejected");
                return Map.of("status", "unauthorized");
            }

            String eventType = payload.path("header").path("event_type").asText("");
            if (!"im.message.receive_v1".equals(eventType)) {
                return Map.of("status", "ignored");
            }
            JsonNode message = payload.path("event").path("message");
            if (!"text".equals(message.path("message_type").asText(""))) {
                return Map.of("status", "ignored");
            }
            String chatId = message.path("chat_id").asText("");
            String senderId = payload.path("event").path("sender")
                    .path("sender_id").path("open_id").asText("unknown");
            // content 是内嵌 JSON 字符串：{"text":"..."}
            String contentJson = message.path("content").asText("{}");
            String text = objectMapper.readTree(contentJson).path("text").asText("");
            // 去除群聊 @机器人 前缀（形如 @_user_1）
            text = text.replaceAll("@_user_\\d+\\s*", "").trim();
            if (chatId.isEmpty() || text.isEmpty()) {
                return Map.of("status", "ignored");
            }

            String answer = botChatService.answer(cfg.getAppKey(), senderId, text);
            replyToChat(cfg, chatId, answer);
            return Map.of("status", "ok");
        } catch (Exception e) {
            log.warn("Feishu bot callback failed: {}", e.getMessage());
            return Map.of("status", "error");
        }
    }

    private boolean verifyToken(BotProperties.Feishu cfg, JsonNode payload) {
        if (!StringUtils.hasText(cfg.getVerificationToken())) {
            return true; // 未配置则不校验（测试/内网场景）
        }
        String token = payload.path("header").path("token").asText("");
        return java.security.MessageDigest.isEqual(
                cfg.getVerificationToken().getBytes(java.nio.charset.StandardCharsets.UTF_8),
                token.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    private void replyToChat(BotProperties.Feishu cfg, String chatId, String answer) {
        String token = tenantAccessToken(cfg);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(token);
        String contentJson;
        try {
            contentJson = objectMapper.writeValueAsString(Map.of("text", answer));
        } catch (Exception e) {
            contentJson = "{\"text\":\"回答序列化失败\"}";
        }
        Map<String, Object> payload = new HashMap<>();
        payload.put("receive_id", chatId);
        payload.put("msg_type", "text");
        payload.put("content", contentJson);
        restTemplate.postForEntity(
                MESSAGE_URL, new HttpEntity<>(payload, headers), String.class);
    }

    private String tenantAccessToken(BotProperties.Feishu cfg) {
        CachedToken cached = tokenCache.get(cfg.getAppId());
        if (cached != null && cached.expiresAt > Instant.now().getEpochSecond() + 60) {
            return cached.token;
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map<String, Object> body = new HashMap<>();
        body.put("app_id", cfg.getAppId());
        body.put("app_secret", cfg.getAppSecret());
        JsonNode response = restTemplate.postForEntity(
                TOKEN_URL, new HttpEntity<>(body, headers), JsonNode.class).getBody();
        String token = response == null ? "" : response.path("tenant_access_token").asText("");
        long expire = response == null ? 0 : response.path("expire").asLong(0);
        if (token.isEmpty()) {
            throw new IllegalStateException("Feishu tenant_access_token 获取失败");
        }
        tokenCache.put(cfg.getAppId(), new CachedToken(token, Instant.now().getEpochSecond() + expire));
        return token;
    }

    private record CachedToken(String token, long expiresAt) {}
}
