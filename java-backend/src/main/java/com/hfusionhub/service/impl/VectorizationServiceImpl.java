package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.Document;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.service.VectorizationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 向量化服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VectorizationServiceImpl implements VectorizationService {

    private final DocumentMapper documentMapper;
    private final RestTemplate restTemplate;

    @Value("${python-ai.engine.url:http://localhost:8001}")
    private String pythonEngineUrl;

    @Value("${python-ai.callback-base-url:http://localhost:8080/api}")
    private String callbackBaseUrl;

    @Value("${python-ai.callback-secret:hfusionhub-callback-secret-key}")
    private String callbackSecret;

    @Override
    public void startVectorization(Long documentId, String model) {
        // 1. 查询文档
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 检查状态 - 允许重新处理处于 PROCESSING 状态的文档（修复之前的卡住问题）
        if (document.getStatus() != null && document.getStatus() == DocumentStatus.PROCESSING.getCode()) {
            log.warn("文档 {} 处于处理中状态，允许重新处理", documentId);
        }

        // 3. 更新状态为处理中
        document.setStatus(DocumentStatus.PROCESSING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);

        // 4. 异步调用Python引擎进行处理
        try {
            callPythonEngine(document, model);
        } catch (Exception e) {
            log.error("调用Python引擎失败", e);
            document.setStatus(DocumentStatus.FAILED.getCode());
            document.setErrorMessage("调用AI引擎失败: " + e.getMessage());
            documentMapper.updateById(document);
            throw new BusinessException("启动向量化失败: " + e.getMessage());
        }
    }

    @Override
    public String getDocumentChunks(Long documentId, Integer page, Integer size, String blockType) {
        try {
            String url = pythonEngineUrl + "/api/chunks/" + documentId
                    + "?page=" + page
                    + "&size=" + size;

            if (blockType != null && !blockType.isEmpty()) {
                url += "&block_type=" + blockType;
            }

            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("获取分块列表失败", e);
            return "{\"code\":500,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    @Override
    public String getChunkDetail(String chunkId) {
        try {
            String url = pythonEngineUrl + "/api/chunks/" + chunkId;
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("获取分块详情失败", e);
            return "{\"code\":500,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    @Override
    public void updateDocumentStatus(Long documentId, String status, Integer chunkCount) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            log.warn("文档不存在: {}", documentId);
            return;
        }

        DocumentStatus docStatus = DocumentStatus.valueOf(status);
        document.setStatus(docStatus.getCode());
        document.setChunkCount(chunkCount);

        if (docStatus == DocumentStatus.COMPLETED) {
            document.setProcessedAt(LocalDateTime.now());
        } else if (docStatus == DocumentStatus.FAILED) {
            document.setErrorMessage("处理失败");
        }

        documentMapper.updateById(document);
        log.info("文档状态已更新: {} -> {}", documentId, status);
    }

    @Override
    public void syncDocumentStatus(Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        try {
            // 查询Python引擎的分块数据
            String url = pythonEngineUrl + "/api/chunks/" + documentId + "?page=1&size=1";
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);

            if (response.getBody() != null) {
                // 解析响应获取total_chunks（Python返回格式：{"success":true, "total_chunks":100, ...}）
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                com.fasterxml.jackson.databind.JsonNode root = mapper.readTree(response.getBody());
                int totalChunks = root.path("total_chunks").asInt(0);

                if (totalChunks > 0) {
                    // 有分块数据，更新为已完成
                    document.setStatus(DocumentStatus.COMPLETED.getCode());
                    document.setChunkCount(totalChunks);
                    document.setProcessedAt(LocalDateTime.now());
                    documentMapper.updateById(document);
                    log.info("同步文档状态成功: {} -> COMPLETED, chunks: {}", documentId, totalChunks);
                } else {
                    log.info("文档 {} 无分块数据，状态不变", documentId);
                }
            }
        } catch (Exception e) {
            log.error("同步文档状态失败: {}", documentId, e);
            throw new BusinessException("同步状态失败: " + e.getMessage());
        }
    }

    @Override
    public int syncAllDocuments() {
        // 查询所有待处理或处理中的文档
        LambdaQueryWrapper<Document> wrapper = new LambdaQueryWrapper<>();
        wrapper.in(Document::getStatus,
                DocumentStatus.PENDING.getCode(),
                DocumentStatus.PROCESSING.getCode());
        List<Document> pendingDocs = documentMapper.selectList(wrapper);

        int updated = 0;
        for (Document doc : pendingDocs) {
            try {
                syncDocumentStatus(doc.getId());
                updated++;
            } catch (Exception e) {
                log.warn("同步文档状态失败: {}", doc.getId(), e);
            }
        }
        return updated;
    }

    @Override
    public void resetDocument(Long documentId) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 只有处理中或失败的状态才允许重置
        if (document.getStatus() != null
                && document.getStatus() != DocumentStatus.PROCESSING.getCode()
                && document.getStatus() != DocumentStatus.FAILED.getCode()) {
            throw new BusinessException("当前状态不允许重置");
        }

        document.setStatus(DocumentStatus.PENDING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);
        log.info("文档状态已重置为待解析: {}", documentId);
    }

    @Override
    public String getTaskStatus(Long documentId) {
        try {
            String url = pythonEngineUrl + "/api/task-status/" + documentId;
            ResponseEntity<String> response = restTemplate.getForEntity(url, String.class);
            return response.getBody();
        } catch (Exception e) {
            log.error("获取任务状态失败: {}", documentId, e);
            return "{\"status\":\"ERROR\",\"message\":\"" + e.getMessage() + "\"}";
        }
    }

    /**
     * 调用Python引擎
     */
    private void callPythonEngine(Document document, String model) {
        String url = pythonEngineUrl + "/api/parse";

        // 构建回调URL，用于Python引擎处理完成后通知Java后端
        String callbackUrl = callbackBaseUrl + "/vectorize/" + document.getId() + "/callback";

        Map<String, Object> request = Map.of(
                "document_id", String.valueOf(document.getId()),
                "file_path", document.getFilePath(),
                "file_type", document.getFileType() != null ? document.getFileType() : "md",
                "knowledge_base_id", document.getKnowledgeBaseId() != null ? document.getKnowledgeBaseId() : 0,
                "callback_url", callbackUrl,
                "callback_secret", callbackSecret,
                "embedding_model", model != null ? model : "ollama"
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Callback-Secret", callbackSecret);

        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

        log.info("调用Python引擎: {}, 回调URL: {}, 模型: {}", url, callbackUrl, model);
        ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);
        log.info("Python引擎响应: {}", response.getBody());
    }
}
