package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

/**
 * 语音 STT/TTS 转发（Batch 10）——登录态用户经 Java 转发到 Python 音频引擎。
 *
 * <p>Java 不处理任何音频逻辑，仅做会话鉴权（/voice/** 不在 SaToken 放行清单）、
 * 内部令牌注入与字节流转发。开关与凭证全部在 Python 侧（VOICE_* 配置，
 * VOICE_ENABLED=false 时 Python 返回 503，此处原样转告）。</p>
 */
@Slf4j
@RestController
@RequestMapping("/voice")
@RequiredArgsConstructor
public class VoiceController {

    private final RestTemplate restTemplate;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String baseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    @GetMapping("/status")
    public R<Map<String, Object>> status() {
        try {
            ResponseEntity<Map> response = restTemplate.exchange(
                    baseUrl + "/api/voice/status",
                    HttpMethod.GET,
                    new HttpEntity<>(internalHeaders()),
                    Map.class);
            return R.ok(response.getBody());
        } catch (Exception e) {
            log.warn("Voice status forward failed: {}", e.getMessage());
            return R.ok(Map.of("enabled", false, "stt", false, "tts", false));
        }
    }

    @PostMapping(value = "/transcribe", consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public R<Map<String, Object>> transcribe(
            @RequestBody byte[] audio,
            @RequestHeader(value = "X-Audio-Filename", required = false, defaultValue = "audio.webm")
            String filename,
            @RequestParam(value = "language", required = false) String language) {
        if (audio == null || audio.length == 0) {
            return R.fail(400, "音频内容为空");
        }
        try {
            // 原始字节体转发（Python /api/voice/transcribe 收原始音频 + X-Audio-Filename 头）
            HttpHeaders headers = internalHeaders();
            headers.set("X-Audio-Filename", filename);
            headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
            String url = baseUrl + "/api/voice/transcribe"
                    + (StringUtils.hasText(language) ? "?language=" + language : "");
            ResponseEntity<Map> response = restTemplate.exchange(
                    url, HttpMethod.POST, new HttpEntity<>(audio, headers), Map.class);
            return R.ok(response.getBody());
        } catch (Exception e) {
            log.warn("Voice transcribe forward failed: {}", e.getMessage());
            return R.fail(503, "语音识别服务暂不可用");
        }
    }

    @PostMapping("/synthesize")
    public ResponseEntity<byte[]> synthesize(@RequestBody Map<String, Object> body) {
        String text = body.get("text") == null ? "" : String.valueOf(body.get("text"));
        if (!StringUtils.hasText(text)) {
            return ResponseEntity.badRequest().build();
        }
        try {
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.setAccept(List.of(MediaType.APPLICATION_OCTET_STREAM, MediaType.ALL));
            ResponseEntity<byte[]> response = restTemplate.exchange(
                    baseUrl + "/api/voice/synthesize",
                    HttpMethod.POST,
                    new HttpEntity<>(body, headers),
                    byte[].class);
            String contentType = String.valueOf(
                    response.getHeaders().getFirst("Content-Type"));
            return ResponseEntity.ok()
                    .contentType(MediaType.parseMediaType(contentType))
                    .body(response.getBody());
        } catch (Exception e) {
            log.warn("Voice synthesize forward failed: {}", e.getMessage());
            return ResponseEntity.internalServerError().build();
        }
    }

    private HttpHeaders internalHeaders() {
        HttpHeaders headers = new HttpHeaders();
        if (internalApiToken != null && !internalApiToken.isBlank()) {
            headers.set("X-Internal-Token", internalApiToken);
        }
        return headers;
    }
}
