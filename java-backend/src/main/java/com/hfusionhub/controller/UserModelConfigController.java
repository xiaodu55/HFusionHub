package com.hfusionhub.controller;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.UserModelConfigDTO;
import com.hfusionhub.dto.UserModelConfigSaveDTO;
import com.hfusionhub.service.UserModelConfigService;
import jakarta.validation.Valid;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/model-config")
@RequiredArgsConstructor
public class UserModelConfigController {

    private final UserModelConfigService modelConfigService;
    private final AiClient aiClient;

    @GetMapping
    public R<UserModelConfigDTO> getMine() {
        return R.ok(modelConfigService.get(JwtUtils.getCurrentUserId()));
    }

    @PutMapping
    public R<UserModelConfigDTO> save(@Valid @RequestBody UserModelConfigSaveDTO dto) {
        return R.ok("模型配置已保存", modelConfigService.save(JwtUtils.getCurrentUserId(), dto));
    }

    @PostMapping("/test")
    public R<Map<String, Object>> test(@Valid @RequestBody UserModelConfigSaveDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        Map<String, Object> runtimeConfig = modelConfigService.resolveRuntimeConfig(userId, dto);
        Map<String, Object> result = aiClient.testUserProvider(runtimeConfig);
        boolean success = Boolean.TRUE.equals(result.get("success"));
        modelConfigService.recordTestResult(userId, success, String.valueOf(result.getOrDefault("message", "")));
        return R.ok(success ? "连接成功" : "连接失败", result);
    }

    @DeleteMapping
    public R<Void> reset() {
        modelConfigService.reset(JwtUtils.getCurrentUserId());
        return R.ok("已恢复系统默认模型", null);
    }
}
