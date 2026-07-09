package com.hfusionhub.bot;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import org.w3c.dom.Element;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 企业微信应用回调（Batch 6，默认关闭）。
 *
 * <p>协议：回调 URL 验证（GET，echostr 解密回显）+ 消息推送（POST，XML 加密）。
 * 签名与 AES-256-CBC 加解密见 {@link WeComCrypto}。回答经 {@link BotChatService}
 * 生成后通过企业微信「应用消息」接口主动发送（access_token 进程内缓存）。</p>
 */
@Slf4j
@RestController
@RequestMapping("/openapi/bots/wecom")
@RequiredArgsConstructor
public class WeComBotController {

    private static final String TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken";
    private static final String SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send";

    private final BotProperties properties;
    private final BotChatService botChatService;
    private final RestTemplate restTemplate;

    private final Map<String, CachedToken> tokenCache = new ConcurrentHashMap<>();

    /** 回调 URL 验证：解密 echostr 后以明文返回。 */
    @GetMapping
    public String verify(@RequestParam("msg_signature") String msgSignature,
                         @RequestParam("timestamp") String timestamp,
                         @RequestParam("nonce") String nonce,
                         @RequestParam("echostr") String echostr) {
        BotProperties.WeCom cfg = properties.getWecom();
        if (!cfg.isEnabled()) {
            return "disabled";
        }
        if (!WeComCrypto.verifySignature(cfg.getToken(), timestamp, nonce, echostr, msgSignature)) {
            log.warn("WeCom callback verify signature rejected");
            return "unauthorized";
        }
        return WeComCrypto.decrypt(cfg.getEncodingAesKey(), echostr);
    }

    /** 消息推送：解密 XML → 回答 → 应用消息主动回复。 */
    @PostMapping
    public Map<String, Object> onMessage(
            @RequestParam("msg_signature") String msgSignature,
            @RequestParam("timestamp") String timestamp,
            @RequestParam("nonce") String nonce,
            @RequestBody String body) {
        BotProperties.WeCom cfg = properties.getWecom();
        if (!cfg.isEnabled()) {
            return Map.of("status", "disabled");
        }
        try {
            Element root = parseXml(body);
            String encrypt = textOf(root, "Encrypt");
            if (!WeComCrypto.verifySignature(cfg.getToken(), timestamp, nonce, encrypt, msgSignature)) {
                log.warn("WeCom bot callback signature rejected");
                return Map.of("status", "unauthorized");
            }
            String plainXml = WeComCrypto.decrypt(cfg.getEncodingAesKey(), encrypt);
            Element plain = parseXml(plainXml);
            String content = textOf(plain, "Content");
            String fromUser = textOf(plain, "FromUserName");
            if (!StringUtils.hasText(content)) {
                return Map.of("status", "ignored");
            }
            String answer = botChatService.answer(cfg.getAppKey(), fromUser, content);
            sendText(cfg, fromUser, answer);
            return Map.of("status", "ok");
        } catch (Exception e) {
            log.warn("WeCom bot callback failed: {}", e.getMessage());
            return Map.of("status", "error");
        }
    }

    private Element parseXml(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        // XXE 防护：禁用外部实体
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute("http://xml.org/sax/features/external-general-entities", false);
        factory.setAttribute("http://xml.org/sax/features/external-parameter-entities", false);
        return factory.newDocumentBuilder()
                .parse(new ByteArrayInputStream(xml.getBytes(java.nio.charset.StandardCharsets.UTF_8)))
                .getDocumentElement();
    }

    private static String textOf(Element root, String tag) {
        var nodes = root.getElementsByTagName(tag);
        return nodes.getLength() == 0 ? "" : nodes.item(0).getTextContent().trim();
    }

    private void sendText(BotProperties.WeCom cfg, String user, String answer) {
        String accessToken = accessToken(cfg);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map<String, Object> payload = new HashMap<>();
        payload.put("touser", user);
        payload.put("msgtype", "text");
        payload.put("agentid", cfg.getAgentId());
        payload.put("text", Map.of("content", answer));
        restTemplate.postForEntity(
                SEND_URL + "?access_token=" + accessToken,
                new HttpEntity<>(payload, headers), String.class);
    }

    private String accessToken(BotProperties.WeCom cfg) {
        CachedToken cached = tokenCache.get(cfg.getCorpId());
        if (cached != null && cached.expiresAt > Instant.now().getEpochSecond() + 60) {
            return cached.token;
        }
        String url = TOKEN_URL + "?corpid=" + cfg.getCorpId() + "&corpsecret=" + cfg.getCorpSecret();
        JsonNode response = restTemplate.getForObject(url, JsonNode.class);
        String token = response == null ? "" : response.path("access_token").asText("");
        int expire = response == null ? 0 : response.path("expires_in").asInt(7200);
        if (token.isEmpty()) {
            throw new IllegalStateException("企业微信 access_token 获取失败");
        }
        tokenCache.put(cfg.getCorpId(), new CachedToken(token, Instant.now().getEpochSecond() + expire));
        return token;
    }

    private record CachedToken(String token, long expiresAt) {}
}
