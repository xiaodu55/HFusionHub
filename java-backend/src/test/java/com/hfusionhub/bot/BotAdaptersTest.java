package com.hfusionhub.bot;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.service.OpenApiService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class BotAdaptersTest {

    // ── DingTalk 签名 ──────────────────────────────────────────────────

    @Test
    void dingTalkSignVerifyAcceptsCorrectSignature() {
        String secret = "secret-key";
        String timestamp = "1700000000000";
        String sign = DingTalkBotController.computeSign(secret, timestamp);
        assertTrue(DingTalkBotController.verifySign(secret, timestamp, sign));
    }

    @Test
    void dingTalkSignVerifyRejectsWrongSignatureAndMissingParts() {
        String sign = DingTalkBotController.computeSign("secret-key", "1700000000000");
        assertFalse(DingTalkBotController.verifySign("other-secret", "1700000000000", sign));
        assertFalse(DingTalkBotController.verifySign("secret-key", "1700000000001", sign));
        assertFalse(DingTalkBotController.verifySign("", "123", sign));
        assertFalse(DingTalkBotController.verifySign("secret", "123", ""));
        assertFalse(DingTalkBotController.verifySign("secret", null, sign));
    }

    // ── WeCom 加解密 round-trip ────────────────────────────────────────

    @Test
    void weComCryptoRoundTrip() {
        // EncodingAESKey 是 43 位 Base64（解码 32 字节）；构造合法 key
        String aesKey = java.util.Base64.getEncoder()
                .encodeToString(new byte[32]).substring(0, 43);
        String plain = "<xml><ToUserName><![CDATA[corp]]></ToUserName>"
                + "<Content><![CDATA[你好，机器人]]></Content></xml>";
        String receiveId = "corp-id-1";
        String timestamp = "1700000000";
        String nonce = "nonce-1";

        String encrypted = WeComCrypto.encrypt(aesKey, plain, receiveId);
        String signature = WeComCrypto.signature("token-1", timestamp, nonce, encrypted);

        assertTrue(WeComCrypto.verifySignature("token-1", timestamp, nonce, encrypted, signature));
        assertFalse(WeComCrypto.verifySignature("token-2", timestamp, nonce, encrypted, signature));

        assertEquals(plain, WeComCrypto.decrypt(aesKey, encrypted));
    }

    @Test
    void weComDecryptRejectsTamperedData() {
        String aesKey = java.util.Base64.getEncoder()
                .encodeToString(new byte[32]).substring(0, 43);
        String encrypted = WeComCrypto.encrypt(aesKey, "<xml/>", "corp");
        byte[] bytes = java.util.Base64.getDecoder().decode(encrypted);
        bytes[30] ^= 0x7F; // 破坏密文
        String tampered = java.util.Base64.getEncoder().encodeToString(bytes);
        try {
            // 解密要么抛异常（填充非法），要么明文被破坏
            assertNotEquals("<xml/>", WeComCrypto.decrypt(aesKey, tampered));
        } catch (IllegalStateException | IllegalArgumentException expected) {
            // 官方协议下大多数篡改会在去填充阶段暴露
        }
    }

    // ── 飞书 challenge（通过控制器 HTTP 语义间接验证解析层） ────────────

    @Test
    void feishuChallengeEchoAndDisabledState() throws Exception {
        BotProperties properties = new BotProperties();
        BotChatService chatService = mock(BotChatService.class);
        FeishuBotController controller = new FeishuBotController(
                properties, chatService, mock(org.springframework.web.client.RestTemplate.class));

        // 未启用：直接返回 disabled
        var disabled = controller.onEvent("{\"type\":\"url_verification\",\"challenge\":\"abc\"}");
        assertEquals("disabled", disabled.get("status"));

        // 启用后：challenge 原样回显
        properties.getFeishu().setEnabled(true);
        var echoed = controller.onEvent("{\"type\":\"url_verification\",\"challenge\":\"abc-123\"}");
        assertEquals("abc-123", echoed.get("challenge"));
    }

    // ── BotChatService ────────────────────────────────────────────────

    @Test
    void botChatServiceDelegatesToOpenApi() {
        OpenApiService openApi = mock(OpenApiService.class);
        BotChatService service = new BotChatService(openApi);

        OpenApiChatResponse ok = new OpenApiChatResponse();
        ok.setContent("这是回答");
        when(openApi.chat(eq("app-key"), any(OpenApiChatRequest.class))).thenReturn(ok);

        assertEquals("这是回答", service.answer("app-key", "user-1", "问题"));
    }

    @Test
    void botChatServiceDegradesGracefully() {
        OpenApiService openApi = mock(OpenApiService.class);
        BotChatService service = new BotChatService(openApi);

        // 未配置 appKey
        assertEquals(BotChatService.MISCONFIGURED_REPLY, service.answer(null, "u", "q"));
        assertEquals(BotChatService.MISCONFIGURED_REPLY, service.answer("  ", "u", "q"));

        // 业务异常 → 受限文案
        when(openApi.chat(anyString(), any(OpenApiChatRequest.class)))
                .thenThrow(new BusinessException(429, "调用频率超限，请稍后重试"));
        String limited = service.answer("app-key", "u", "q");
        assertTrue(limited.contains("调用受限"));

        // 其他异常 → 兜底文案
        when(openApi.chat(anyString(), any(OpenApiChatRequest.class)))
                .thenThrow(new RuntimeException("boom"));
        assertEquals(BotChatService.ERROR_REPLY, service.answer("app-key", "u", "q"));

        // 空回答 → 兜底文案
        OpenApiChatResponse empty = new OpenApiChatResponse();
        empty.setContent("");
        when(openApi.chat(anyString(), any(OpenApiChatRequest.class))).thenReturn(empty);
        assertEquals(BotChatService.ERROR_REPLY, service.answer("app-key", "u", "q"));
    }

    // ── 默认关闭 ───────────────────────────────────────────────────────

    @Test
    void allBotsDisabledByDefault() {
        BotProperties properties = new BotProperties();
        assertFalse(properties.getDingtalk().isEnabled());
        assertFalse(properties.getFeishu().isEnabled());
        assertFalse(properties.getWecom().isEnabled());
    }
}
