package com.hfusionhub.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.ChunkDTO;
import com.hfusionhub.dto.ChunkPageDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.service.VectorizationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

/**
 * 向量化控制器
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "向量化管理", description = "文档向量化相关接口")
@RestController
@RequestMapping("/vectorize")
@RequiredArgsConstructor
public class VectorizationController {

    private final VectorizationService vectorizationService;
    private final ObjectMapper objectMapper;

    @Value("${python-ai.callback-secret:}")
    private String callbackSecret;

    @Operation(summary = "获取可用的嵌入模型列表")
    @GetMapping("/models")
    public R<Map<String, Object>> getModels() {
        List<Map<String, Object>> models = new ArrayList<>();

        // Ollama 本地模型
        Map<String, Object> ollamaModel = new HashMap<>();
        ollamaModel.put("id", "ollama");
        ollamaModel.put("name", "Ollama - bge-m3:latest");
        ollamaModel.put("type", "local");
        ollamaModel.put("dimension", 1024);
        ollamaModel.put("description", "本地 Ollama 嵌入模型 (BGE-M3)");
        models.add(ollamaModel);

        Map<String, Object> result = new HashMap<>();
        result.put("models", models);

        return R.ok(result);
    }

    @Operation(summary = "触发文档向量化")
    @PostMapping("/{documentId}")
    public R<String> startVectorization(
            @Parameter(description = "文档ID") @PathVariable Long documentId,
            @RequestBody(required = false) Map<String, String> body) {
        String model = body != null ? body.get("model") : null;
        vectorizationService.startVectorization(documentId, model);
        return R.ok("开始处理");
    }

    @Operation(summary = "获取文档分块列表")
    @GetMapping("/{documentId}/chunks")
    public R<ChunkPageDTO> getDocumentChunks(
            @Parameter(description = "文档ID") @PathVariable Long documentId,
            @Parameter(description = "页码") @RequestParam(defaultValue = "1") Integer page,
            @Parameter(description = "每页大小") @RequestParam(defaultValue = "20") Integer size,
            @Parameter(description = "块类型筛选") @RequestParam(required = false) String blockType) {
        ChunkPageDTO result = vectorizationService.getDocumentChunks(documentId, page, size, blockType);
        return R.ok(result);
    }

    @Operation(summary = "获取单个分块详情")
    @GetMapping("/chunks/{chunkId}")
    public R<ChunkDTO> getChunkDetail(@Parameter(description = "分块ID") @PathVariable String chunkId) {
        ChunkDTO result = vectorizationService.getChunkDetail(chunkId);
        return R.ok(result);
    }

    @Operation(summary = "回调：更新文档处理状态")
    @PostMapping("/{documentId}/callback")
    public R<String> updateStatus(
            @Parameter(description = "文档ID") @PathVariable Long documentId,
            @RequestBody String rawBody,
            @RequestHeader(value = "X-Callback-Secret", required = false) String secret,
            @RequestHeader(value = "X-Callback-Signature", required = false) String signature) {
        // 1. 验证回调密钥（常量时间比较）
        if (callbackSecret == null
                || callbackSecret.isBlank()
                || secret == null
                || !MessageDigest.isEqual(
                        callbackSecret.getBytes(StandardCharsets.UTF_8), secret.getBytes(StandardCharsets.UTF_8))) {
            log.warn("回调密钥验证失败: documentId={}", documentId);
            return R.fail("回调密钥无效");
        }

        // 2. 验证 HMAC-SHA256 签名
        if (!verifyHmacSignature(rawBody, callbackSecret, signature)) {
            log.warn("回调签名验证失败: documentId={}", documentId);
            return R.fail("回调签名无效");
        }

        // 3. 反序列化并处理
        try {
            DocumentIndexCallbackDTO body = objectMapper.readValue(rawBody, DocumentIndexCallbackDTO.class);
            vectorizationService.updateDocumentStatus(documentId, body);
            return R.ok("状态已更新");
        } catch (Exception e) {
            log.error("回调请求体反序列化失败: documentId={}", documentId, e);
            return R.fail("回调请求体格式错误");
        }
    }

    /**
     * 验证 HMAC-SHA256 签名
     */
    private boolean verifyHmacSignature(String payload, String secret, String signature) {
        if (signature == null || signature.isBlank()) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            SecretKeySpec keySpec = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
            mac.init(keySpec);
            byte[] computed = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            String expected = Base64.getEncoder().encodeToString(computed);
            return MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.UTF_8), signature.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.error("HMAC 签名验证失败", e);
            return false;
        }
    }

    @Operation(summary = "同步文档状态 - 从Python引擎查询实际分块数更新状态")
    @PostMapping("/{documentId}/sync-status")
    public R<String> syncDocumentStatus(@Parameter(description = "文档ID") @PathVariable Long documentId) {
        vectorizationService.syncDocumentStatus(documentId);
        return R.ok("状态已同步");
    }

    @Operation(summary = "批量同步所有待解析/处理中文档的状态")
    @PostMapping("/sync-all")
    public R<String> syncAllDocuments() {
        int updated = vectorizationService.syncAllDocuments();
        return R.ok("同步完成，已更新 " + updated + " 个文档");
    }

    @Operation(summary = "重置文档状态为待解析")
    @PostMapping("/{documentId}/reset")
    public R<String> resetDocument(@Parameter(description = "文档ID") @PathVariable Long documentId) {
        vectorizationService.resetDocument(documentId);
        return R.ok("已重置为待解析状态");
    }

    @Operation(summary = "查询文档处理任务状态")
    @GetMapping("/{documentId}/status")
    public R<String> getTaskStatus(@Parameter(description = "文档ID") @PathVariable Long documentId) {
        String status = vectorizationService.getTaskStatus(documentId);
        return R.ok(status);
    }
}
