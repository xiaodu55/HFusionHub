package com.hfusionhub.service.impl;

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

    @Override
    public void startVectorization(Long documentId) {
        // 1. 查询文档
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            throw new BusinessException("文档不存在");
        }

        // 2. 检查状态
        if (document.getStatus() != null && document.getStatus() == DocumentStatus.PROCESSING.getCode()) {
            throw new BusinessException("文档正在处理中");
        }

        // 3. 更新状态为处理中
        document.setStatus(DocumentStatus.PROCESSING.getCode());
        document.setErrorMessage(null);
        documentMapper.updateById(document);

        // 4. 异步调用Python引擎进行处理
        try {
            callPythonEngine(document);
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

    /**
     * 调用Python引擎
     */
    private void callPythonEngine(Document document) {
        String url = pythonEngineUrl + "/api/parse";

        Map<String, Object> request = Map.of(
                "document_id", String.valueOf(document.getId()),
                "file_path", document.getFilePath(),
                "file_type", document.getFileType() != null ? document.getFileType() : "md"
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

        log.info("调用Python引擎: {}", url);
        ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, entity, String.class);
        log.info("Python引擎响应: {}", response.getBody());
    }
}
