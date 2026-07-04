package com.hfusionhub.controller;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.util.Map;

/**
 * 评估中枢（eval_harness）API 网关。
 *
 * <p>浏览器只访问 Java 后端；本控制器把 python-ai 的评估端点统一暴露在
 * /api/eval-harness 下。评估会真实驱动生产链路（SSE 对话 + 检索），仅限
 * 知识库所有者执行；KB 归属校验与 /rag 观测网关一致。</p>
 */
@Slf4j
@RestController
@RequestMapping("/eval-harness")
public class EvalHarnessController {

    private final RestTemplate restTemplate;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String aiServiceBaseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    public EvalHarnessController(RestTemplate restTemplate, KnowledgeBaseMapper knowledgeBaseMapper) {
        this.restTemplate = restTemplate;
        this.knowledgeBaseMapper = knowledgeBaseMapper;
    }

    /** 运行一次评估（同步；样本量大时耗时与并发配置相关）。 */
    @PostMapping("/run")
    public R<Map> run(@RequestBody Map<String, Object> body) {
        Long knowledgeBaseId = ((Number) body.getOrDefault("knowledge_base_id", 0)).longValue();
        requireOwnedKnowledgeBase(knowledgeBaseId);
        return R.ok(post("/api/eval-harness/run", body));
    }

    /** 重放评分（不重打生产链路）。 */
    @PostMapping("/score")
    public R<Map> score(@RequestBody Map<String, Object> body) {
        return R.ok(post("/api/eval-harness/score", body));
    }

    /** 运行文件列表。 */
    @GetMapping("/runs")
    public R<Map> listRuns() {
        String url = UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl)
                .path("/api/eval-harness/runs").toUriString();
        return R.ok(get(url));
    }

    /** markdown 评估报告。 */
    @GetMapping("/report")
    public R<Map> report(@org.springframework.web.bind.annotation.RequestParam String runFile) {
        String url = UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl)
                .path("/api/eval-harness/report")
                .queryParam("run_file", runFile).toUriString();
        return R.ok(get(url));
    }

    /** 自包含 HTML 幻灯片（返回原文，前端以 blob 下载）。 */
    @GetMapping("/slides")
    public R<Map> slides(@org.springframework.web.bind.annotation.RequestParam String runFile) {
        String url = UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl)
                .path("/api/eval-harness/slides")
                .queryParam("run_file", runFile).toUriString();
        return R.ok(get(url));
    }

    /** A/B 回归门禁对比。 */
    @PostMapping("/diff")
    public R<Map> diff(@RequestBody Map<String, Object> body) {
        return R.ok(post("/api/eval-harness/diff", body));
    }

    /** 数据集白名单列表。 */
    @GetMapping("/datasets")
    public R<Map> listDatasets() {
        String url = UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl)
                .path("/api/eval-harness/datasets").toUriString();
        return R.ok(get(url));
    }

    // ── forwarding helpers（与 RagObservabilityController 同款）─────────

    private Map get(String url) {
        try {
            Map response = restTemplate
                    .exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class)
                    .getBody();
            if (response == null) {
                throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "评估服务返回为空");
            }
            return response;
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            log.error("eval-harness request failed: {}", url, exception);
            throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "评估服务不可用");
        }
    }

    private Map post(String path, Map<String, Object> body) {
        try {
            Map response = restTemplate
                    .exchange(UriComponentsBuilder.fromHttpUrl(aiServiceBaseUrl).path(path).toUriString(),
                            HttpMethod.POST,
                            new HttpEntity<>(body, jsonHeaders()),
                            Map.class)
                    .getBody();
            if (response == null) {
                throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "评估服务返回为空");
            }
            return response;
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            log.error("eval-harness post failed: {}", path, exception);
            throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "评估服务不可用");
        }
    }

    private HttpHeaders internalHeaders() {
        HttpHeaders headers = new HttpHeaders();
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        headers.set("X-Internal-Token", internalApiToken);
        headers.set("X-Tenant-Id", "1");
        return headers;
    }

    private HttpHeaders jsonHeaders() {
        HttpHeaders headers = internalHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
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
}
