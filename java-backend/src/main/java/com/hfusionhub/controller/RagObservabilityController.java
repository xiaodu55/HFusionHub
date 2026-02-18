package com.hfusionhub.controller;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
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
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String aiServiceBaseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    @GetMapping("/traces")
    public R<Map> listTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) Long knowledgeBaseId,
            @RequestParam(defaultValue = "false") boolean errorOnly,
            @RequestParam(required = false) String query,
            @RequestParam(required = false) String source
    ) {
        requireOwnedKnowledgeBase(knowledgeBaseId);
        if (limit < 1 || limit > 200) {
            throw new BusinessException("limit 必须在 1 到 200 之间");
        }
        if (offset < 0 || offset > 1000) {
            throw new BusinessException("offset 必须在 0 到 1000 之间");
        }
        return R.ok(get(getTraceResourceBuilder("/api/rag/traces")
                .queryParam("limit", limit)
                .queryParam("offset", offset)
                .queryParamIfPresent("knowledge_base_id", java.util.Optional.ofNullable(knowledgeBaseId))
                .queryParam("error_only", errorOnly)
                .queryParamIfPresent("query", java.util.Optional.ofNullable(query))
                .queryParamIfPresent("source", java.util.Optional.ofNullable(source))
                .toUriString()));
    }

    @GetMapping("/traces/stats")
    public R<Map> traceStats(
            @RequestParam(defaultValue = "7") int days,
            @RequestParam Long knowledgeBaseId) {
        requireOwnedKnowledgeBase(knowledgeBaseId);
        if (days < 1 || days > 30) {
            throw new BusinessException("days 必须在 1 到 30 之间");
        }
        return R.ok(get(getTraceResourceBuilder("/api/rag/traces/stats")
                .queryParam("days", days)
                .queryParam("knowledge_base_id", knowledgeBaseId)
                .toUriString()));
    }

    @GetMapping("/traces/export")
    public R<Map> exportTraces(
            @RequestParam(defaultValue = "json") String format,
            @RequestParam(required = false) Long knowledgeBaseId,
            @RequestParam(defaultValue = "false") boolean errorOnly,
            @RequestParam(required = false) String query,
            @RequestParam(required = false) String source
    ) {
        requireOwnedKnowledgeBase(knowledgeBaseId);
        if (!"json".equalsIgnoreCase(format) && !"csv".equalsIgnoreCase(format)) {
            throw new BusinessException("format 只能是 json 或 csv");
        }
        return R.ok(get(getTraceResourceBuilder("/api/rag/traces/export")
                .queryParam("format", format)
                .queryParamIfPresent("knowledge_base_id", java.util.Optional.ofNullable(knowledgeBaseId))
                .queryParam("error_only", errorOnly)
                .queryParamIfPresent("query", java.util.Optional.ofNullable(query))
                .queryParamIfPresent("source", java.util.Optional.ofNullable(source))
                .toUriString()));
    }

    @GetMapping("/traces/{traceId}")
    public R<Map> getTrace(@PathVariable String traceId, @RequestParam Long knowledgeBaseId) {
        requireOwnedKnowledgeBase(knowledgeBaseId);
        Map trace = get(getTraceResourceBuilder("/api/rag/traces/" + traceId)
                .queryParam("knowledge_base_id", knowledgeBaseId)
                .toUriString());
        Object traceKbId = trace.get("knowledge_base_id");
        if (!(traceKbId instanceof Number) || ((Number) traceKbId).longValue() != knowledgeBaseId) {
            throw new BusinessException("检索记录不存在或无权访问");
        }
        return R.ok(trace);
    }

    @PostMapping("/evaluate")
    public R<Map> evaluate(@RequestBody Map<String, Object> request) {
        try {
            Long knowledgeBaseId = requiredKnowledgeBaseId(request.get("knowledge_base_id"));
            requireOwnedKnowledgeBase(knowledgeBaseId);
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            addInternalToken(headers);
            Map response = restTemplate.postForObject(
                    aiServiceBaseUrl + "/api/rag/evaluate",
                    new HttpEntity<>(request, headers),
                    Map.class
            );
            return R.ok(response);
        } catch (Exception exception) {
            if (exception instanceof BusinessException businessException) {
                throw businessException;
            }
            log.error("RAG evaluation request failed", exception);
            throw new BusinessException("RAG 评测服务不可用");
        }
    }

    @GetMapping("/evaluation-runs")
    public R<Map> listEvaluationRuns(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(required = false) Long knowledgeBaseId
    ) {
        requireOwnedKnowledgeBase(knowledgeBaseId);
        if (limit < 1 || limit > 200) {
            throw new BusinessException("limit 必须在 1 到 200 之间");
        }
        return R.ok(get(getTraceResourceBuilder("/api/rag/evaluation-runs")
                .queryParam("limit", limit)
                .queryParamIfPresent("knowledge_base_id", java.util.Optional.ofNullable(knowledgeBaseId))
                .toUriString()));
    }

    private Map get(String url) {
        try {
            Map response = restTemplate.exchange(
                    url, org.springframework.http.HttpMethod.GET,
                    new HttpEntity<>(internalHeaders()), Map.class).getBody();
            if (response == null) {
                throw new BusinessException("RAG 服务返回为空");
            }
            return response;
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            log.error("RAG observability request failed: {}", url, exception);
            throw new BusinessException("RAG 调试服务不可用");
        }
    }

    private UriComponentsBuilder getTraceResourceBuilder(String path) {
        return UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl).path(path);
    }

    private void requireOwnedKnowledgeBase(Long knowledgeBaseId) {
        if (knowledgeBaseId == null || knowledgeBaseId < 1) {
            throw new BusinessException("knowledgeBaseId 必须提供");
        }
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (knowledgeBase == null || !knowledgeBase.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权访问该知识库");
        }
    }

    private Long requiredKnowledgeBaseId(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String string) {
            try {
                return Long.valueOf(string);
            } catch (NumberFormatException ignored) {
                // Fall through to the same client-facing validation error.
            }
        }
        throw new BusinessException("knowledge_base_id 必须提供");
    }

    private HttpHeaders internalHeaders() {
        HttpHeaders headers = new HttpHeaders();
        addInternalToken(headers);
        return headers;
    }

    private void addInternalToken(HttpHeaders headers) {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException("PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        headers.set("X-Internal-Token", internalApiToken);
    }
}
