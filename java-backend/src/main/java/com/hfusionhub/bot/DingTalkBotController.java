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
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

/**
 * 钉钉机器人回调（Batch 6，企业内部机器人 HTTP 模式，默认关闭）。
 *
 * <p>回调校验：请求头 {@code timestamp} + {@code sign}，其中
 * {@code sign = Base64(HmacSHA256(appSecret, timestamp + "\n" + appSecret))}。
 * 回答经 {@link BotChatService}（开放 API 链路）生成后回传到消息体自带的
 * {@code sessionWebhook}。</p>
 */
@Slf4j
@RestController
@RequestMapping("/openapi/bots/dingtalk")
@RequiredArgsConstructor
public class DingTalkBotController {

    private final BotProperties properties;
    private final BotChatService botChatService;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @PostMapping
    public Map<String, Object> onMessage(
            @RequestHeader(value = "timestamp", required = false) String timestamp,
            @RequestHeader(value = "sign", required = false) String sign,
            @RequestBody String body) {
        BotProperties.DingTalk cfg = properties.getDingtalk();
        if (!cfg.isEnabled()) {
            return Map.of("status", "disabled");
        }
        try {
            JsonNode payload = objectMapper.readTree(body);
            if (!verifySign(cfg.getAppSecret(), timestamp, sign)) {
                log.warn("DingTalk bot callback signature rejected");
                return Map.of("status", "unauthorized");
            }
            String text = payload.path("text").path("content").asText("").trim();
            String sender = payload.path("senderStaffId").asText("unknown");
            String webhook = payload.path("sessionWebhook").asText("");
            if (text.isEmpty() || webhook.isEmpty()) {
                return Map.of("status", "ignored");
            }
            String answer = botChatService.answer(cfg.getAppKey(), sender, text);
            replyToWebhook(webhook, answer);
            return Map.of("status", "ok");
        } catch (Exception e) {
            log.warn("DingTalk bot callback failed: {}", e.getMessage());
            return Map.of("status", "error");
        }
    }

    private void replyToWebhook(String webhook, String answer) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map<String, Object> payload = new HashMap<>();
        payload.put("msgtype", "text");
        payload.put("text", Map.of("content", answer));
        restTemplate.postForEntity(webhook, new HttpEntity<>(payload, headers), String.class);
    }

    /** 钉钉回调加签校验：HMAC-SHA256(secret, timestamp + "\n" + secret) 再 Base64。 */
    static boolean verifySign(String secret, String timestamp, String sign) {
        if (!StringUtils.hasText(secret) || !StringUtils.hasText(timestamp)
                || !StringUtils.hasText(sign)) {
            return false;
        }
        try {
            String expectedBase64 = computeSign(secret, timestamp);
            // 常量时间比较，防时序攻击
            return java.security.MessageDigest.isEqual(
                    expectedBase64.getBytes(StandardCharsets.UTF_8),
                    sign.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.warn("DingTalk sign computation failed: {}", e.getMessage());
            return false;
        }
    }

    static String computeSign(String secret, String timestamp) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] expected = mac.doFinal((timestamp + "\n" + secret).getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(expected);
        } catch (Exception e) {
            throw new IllegalStateException("DingTalk sign computation failed", e);
        }
    }
}
