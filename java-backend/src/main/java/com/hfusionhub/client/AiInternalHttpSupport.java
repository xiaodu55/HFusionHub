package com.hfusionhub.client;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.service.UserModelConfigService;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

/**
 * AI Client 共享 HTTP 管道（包私有，第五十八批从 AiClient 抽取）。
 *
 * <p>内部鉴权头（internal token + traceId + 租户上下文）、服务基址、
 * 用户供应商配置注入与 clearance 映射——AiClient 与领域客户端
 * （AiBidClient）共用，保证头构造逻辑全仓只有一份实现，不会漂移。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
final class AiInternalHttpSupport {

    private final UserModelConfigService userModelConfigService;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String baseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    AiInternalHttpSupport(UserModelConfigService userModelConfigService) {
        this.userModelConfigService = userModelConfigService;
    }

    String baseUrl() {
        return baseUrl;
    }

    HttpHeaders internalHeaders() {
        HttpHeaders headers = new HttpHeaders();
        addInternalToken(headers);
        return headers;
    }

    void addUserProviderConfig(Map<String, Object> request, Long userId) {
        if (userId == null || userId <= 0) return;
        Map<String, Object> providerConfig = userModelConfigService.getRuntimeConfig(userId);
        if (!providerConfig.isEmpty()) request.put("provider_config", providerConfig);
    }

    /** user_role → clearance 映射（Python 侧等级模型：admin 全 clearance，其余 general）。 */
    String mapClearance(String userRole) {
        return "admin".equalsIgnoreCase(userRole) ? "admin" : "general";
    }

    private void addInternalToken(HttpHeaders headers) {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        headers.set("X-Internal-Token", internalApiToken);
        // Propagate distributed trace ID to Python AI service
        String traceId = com.hfusionhub.config.TraceContext.getTraceId();
        if (traceId != null) {
            headers.set(com.hfusionhub.config.TraceContext.HEADER_NAME, traceId);
        }
        // Propagate tenant context to Python AI
        Long tenantId = com.hfusionhub.tenant.TenantContext.getTenantId();
        if (tenantId != null) {
            headers.set("X-Tenant-Id", tenantId.toString());
        }
    }
}
