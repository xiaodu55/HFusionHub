package com.hfusionhub.controller;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.Map;

/**
 * RAG 调试与评测 API 网关。
 *
 * 浏览器只访问 Java 后端；该控制器将内部 Python AI 服务的调试接口统一
 * 暴露在 /api/rag 下，避免前端依赖 Python 服务的端口和部署地址。
 */
@Slf4j
@RestController
@RequestMapping("/rag")
@RequiredArgsConstructor
public class RagObservabilityController {

    private final RestTemplate restTemplate;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String aiServiceBaseUrl;

    @GetMapping("/traces")
    public R<Map> listTraces(@RequestParam(defaultValue = "50") int limit) {
        if (limit < 1 || limit > 200) {
            throw new BusinessException("limit 必须在 1 到 200 之间");
        }
        String url = UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl)
                .path("/api/rag/traces")
                .queryParam("limit", limit)
                .toUriString();
        return R.ok(get(url));
    }

    @GetMapping("/traces/stats")
    public R<Map> traceStats() {
        return R.ok(get(aiServiceBaseUrl + "/api/rag/traces/stats"));
    }

    @GetMapping("/traces/{traceId}")
    public R<Map> getTrace(@PathVariable String traceId) {
        return R.ok(get(aiServiceBaseUrl + "/api/rag/traces/" + traceId));
    }

    @PostMapping("/evaluate")
    public R<Map> evaluate(@RequestBody Map<String, Object> request) {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            Map response = restTemplate.postForObject(
                    aiServiceBaseUrl + "/api/rag/evaluate",
                    new HttpEntity<>(request, headers),
                    Map.class
            );
            return R.ok(response);
        } catch (Exception exception) {
            log.error("RAG evaluation request failed", exception);
            throw new BusinessException("RAG 评测服务不可用：" + exception.getMessage());
        }
    }

    private Map get(String url) {
        try {
            Map response = restTemplate.getForObject(url, Map.class);
            if (response == null) {
                throw new BusinessException("RAG 服务返回为空");
            }
            return response;
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            log.error("RAG observability request failed: {}", url, exception);
            throw new BusinessException("RAG 调试服务不可用：" + exception.getMessage());
        }
    }
}
