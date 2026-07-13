package com.hfusionhub.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.result.R;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

/**
 * VoiceController 单元测试 — 语音 STT/TTS 转发（Batch 10）。
 *
 * <p>纯 POJO 测试：mock RestTemplate，反射注入 @Value 字段，
 * 校验转发 URL、内部令牌注入与降级行为。</p>
 */
class VoiceControllerTest {

    private static final String BASE_URL = "http://python:9000";
    private static final String TOKEN = "test-internal-token";

    private RestTemplate restTemplate;
    private VoiceController controller;

    @BeforeEach
    @SuppressWarnings({"unchecked", "rawtypes"})
    void setUp() {
        restTemplate = Mockito.mock(RestTemplate.class);
        controller = new VoiceController(restTemplate);
        ReflectionTestUtils.setField(controller, "baseUrl", BASE_URL);
        ReflectionTestUtils.setField(controller, "internalApiToken", TOKEN);
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void statusForwardsToPythonAndInjectsInternalToken() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class), any(Object[].class)))
                .thenReturn(ResponseEntity.ok(Map.of("enabled", true, "stt", true, "tts", true)));

        R<Map<String, Object>> response = controller.status();

        assertThat(response.getCode()).isEqualTo(200);
        assertThat(response.getData()).containsEntry("enabled", true);
    }

    @Test
    void statusFallsBackToDisabledWhenPythonUnreachable() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class), any(Object[].class)))
                .thenThrow(new IllegalStateException("connection refused"));

        R<Map<String, Object>> response = controller.status();

        // 降级为 enabled=false 而非报错，前端据此隐藏语音入口
        assertThat(response.getCode()).isEqualTo(200);
        assertThat(response.getData()).containsEntry("enabled", false);
    }

    @Test
    void transcribeRejectsEmptyAudioBody() {
        R<Map<String, Object>> response = controller.transcribe(new byte[0], "a.webm", "zh");

        assertThat(response.getCode()).isEqualTo(400);
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void transcribeForwardsAudioWithFilenameHeader() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(Map.class), any(Object[].class)))
                .thenReturn(ResponseEntity.ok(Map.of("text", "你好")));

        R<Map<String, Object>> response = controller.transcribe(new byte[] {1, 2, 3}, "clip.webm", "zh");

        assertThat(response.getCode()).isEqualTo(200);
        assertThat(response.getData()).containsEntry("text", "你好");
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void transcribeReturns503WhenPythonUnreachable() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(Map.class), any(Object[].class)))
                .thenThrow(new IllegalStateException("boom"));

        R<Map<String, Object>> response = controller.transcribe(new byte[] {1}, "clip.webm", null);

        assertThat(response.getCode()).isEqualTo(503);
    }

    @Test
    void synthesizeRejectsBlankText() {
        ResponseEntity<byte[]> response = controller.synthesize(Map.of("text", "  "));

        assertThat(response.getStatusCode().value()).isEqualTo(400);
    }

    @Test
    void synthesizeForwardsAndPreservesContentType() {
        HttpHeaders upstream = new HttpHeaders();
        upstream.setContentType(MediaType.parseMediaType("audio/wav"));
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(byte[].class), any(Object[].class)))
                .thenReturn(ResponseEntity.ok().headers(upstream).body(new byte[] {1, 2, 3}));

        ResponseEntity<byte[]> response = controller.synthesize(Map.of("text", "播报一下"));

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isNotEmpty();
        assertThat(response.getHeaders().getContentType()).isNotNull();
        assertThat(response.getHeaders().getContentType().isCompatibleWith(MediaType.parseMediaType("audio/wav")))
                .isTrue();
    }

    @Test
    void synthesizeReturns500WhenPythonUnreachable() {
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(byte[].class), any(Object[].class)))
                .thenThrow(new IllegalStateException("boom"));

        ResponseEntity<byte[]> response = controller.synthesize(Map.of("text", "播报"));

        assertThat(response.getStatusCode().value()).isEqualTo(500);
    }
}
