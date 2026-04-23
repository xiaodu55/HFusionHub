package com.hfusionhub.controller;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.result.R;
import java.io.File;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * System diagnostics — preflight checks for document parsing readiness.
 */
@Slf4j
@RestController
@RequestMapping("/system")
@RequiredArgsConstructor
public class SystemController {

    private final AiClient aiClient;

    @Value("${python-ai.internal-token:}")
    private String internalToken;

    @Value("${python-ai.callback-secret:}")
    private String callbackSecret;

    @Value("${python-ai.base-url:http://localhost:9000}")
    private String pythonBaseUrl;

    @GetMapping("/ai-health")
    public R<Map<String, Object>> aiHealth() {
        Map<String, Object> checks = new LinkedHashMap<>();

        // 1. Python AI reachability
        boolean pythonReachable = aiClient.isHealthy();
        checks.put("python_ai_reachable", pythonReachable);
        checks.put("python_ai_url", pythonBaseUrl);

        // 2. Token configuration
        boolean tokenConfigured = internalToken != null && !internalToken.isBlank();
        checks.put("internal_token_configured", tokenConfigured);
        if (!tokenConfigured) {
            checks.put("internal_token_hint", "请在启动 Java 和 Python 的终端中设置相同的 PYTHON_AI_INTERNAL_TOKEN");
        }

        // 3. Callback secret
        boolean secretConfigured = callbackSecret != null && !callbackSecret.isBlank();
        checks.put("callback_secret_configured", secretConfigured);
        if (!secretConfigured) {
            checks.put("callback_secret_hint", "请设置 CALLBACK_SECRET 环境变量");
        }

        // 4. Upload directory
        String uploadDir = System.getProperty("user.dir") + File.separator + "uploads" + File.separator + "documents";
        File dir = new File(uploadDir);
        checks.put("upload_dir", uploadDir);
        checks.put("upload_dir_exists", dir.exists());
        checks.put("upload_dir_writable", dir.exists() && dir.canWrite());

        // 5. Overall status
        boolean allOk = pythonReachable && tokenConfigured && secretConfigured;
        checks.put("ready", allOk);
        if (!allOk) {
            StringBuilder hint = new StringBuilder("以下问题需要修复：");
            if (!pythonReachable) hint.append(" Python AI 不可达；");
            if (!tokenConfigured) hint.append(" 内部令牌未配置；");
            if (!secretConfigured) hint.append(" 回调密钥未配置；");
            checks.put("summary", hint.toString().trim());
        } else {
            checks.put("summary", "所有检查通过，AI 服务就绪");
        }

        return R.ok(checks);
    }

    /**
     * Runtime state intended for the model center.  The Python service filters
     * secrets before returning this data; Java only proxies it across the
     * authenticated application boundary.
     */
    @GetMapping("/ai-runtime")
    public R<Map<String, Object>> aiRuntime() {
        return R.ok(aiClient.getRuntimeOverview());
    }
}
