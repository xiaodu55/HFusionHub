package com.hfusionhub.service.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.DocumentChunkCallbackDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentChunk;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.Collections;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 文档索引回调持久化（自 VectorizationServiceImpl 收口，第二十五批 God class
 * 拆分）：Python 引擎（arq worker）完成/失败经签名回调进入，这里在同一事务内
 * 完成 document/document_index_job 终态落库、V2 分块元数据整体替换与用量结算。
 *
 * <p>解析编排（发起/恢复/对账/同步）仍在 {@link VectorizationServiceImpl}；
 * INDEX_CHUNKS 账本生命周期经 {@link IndexChunkLedger} 共享。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VectorizationCallbackService {

    private final DocumentMapper documentMapper;
    private final DocumentIndexJobMapper documentIndexJobMapper;
    private final DocumentChunkMapper documentChunkMapper;
    private final IndexChunkLedger indexChunkLedger;
    private final ObjectMapper objectMapper;

    @Transactional
    public void updateDocumentStatus(Long documentId, DocumentIndexCallbackDTO callback) {
        // Signed callbacks intentionally do not need a client-supplied tenant
        // header. Bootstrap the tenant from durable document ownership under a
        // narrowly scoped system lookup, then run all callback writes inside
        // that tenant boundary.
        Long tenantId = resolveDocumentTenantById(documentId);
        if (tenantId == null) {
            log.warn("Cannot resolve tenant for document callback: documentId={}", documentId);
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            updateDocumentStatusInTenant(documentId, callback);
            return null;
        });
    }

    private void updateDocumentStatusInTenant(Long documentId, DocumentIndexCallbackDTO callback) {
        Document document = documentMapper.selectById(documentId);
        if (document == null) {
            log.warn("文档不存在: {}", documentId);
            return;
        }

        DocumentIndexJob currentJob = documentIndexJobMapper.selectLatestByDocumentId(documentId);
        if (currentJob == null) {
            log.warn("忽略没有任务记录的索引回调: documentId={}", documentId);
            return;
        }
        if (callback.getIndexVersion() == null || !callback.getIndexVersion().equals(currentJob.getIndexVersion())) {
            log.warn(
                    "忽略过期索引回调: documentId={}, callbackVersion={}, currentVersion={}",
                    documentId,
                    callback.getIndexVersion(),
                    currentJob.getIndexVersion());
            return;
        }
        if (!"PROCESSING".equals(currentJob.getStatus())) {
            log.info("忽略已结束任务的重复索引回调: documentId={}, status={}", documentId, currentJob.getStatus());
            return;
        }

        DocumentStatus docStatus;
        try {
            docStatus = DocumentStatus.valueOf(callback.getStatus());
        } catch (Exception e) {
            throw new BusinessException("无效的索引回调状态: " + callback.getStatus());
        }
        int chunkCount = callback.getChunkCount() == null ? 0 : callback.getChunkCount();
        if (docStatus == DocumentStatus.COMPLETED
                && (callback.getChunks() == null || callback.getChunks().size() != chunkCount)) {
            throw new BusinessException("索引完成回调缺少完整的分块元数据");
        }

        document.setStatus(docStatus.getCode());
        document.setChunkCount(chunkCount);

        if (docStatus == DocumentStatus.COMPLETED) {
            document.setProcessedAt(LocalDateTime.now());
            document.setErrorMessage(null);
            // Replace metadata only after the worker has completed.  This is a
            // single database transaction, so citations never observe a mix of
            // an old and a new index version.
            documentChunkMapper.deleteByDocumentId(documentId);
            for (DocumentChunkCallbackDTO callbackChunk : callback.getChunks()) {
                documentChunkMapper.insert(toDocumentChunk(document, currentJob, callbackChunk));
            }
        } else if (docStatus == DocumentStatus.FAILED) {
            document.setErrorMessage(truncate(callback.getMessage(), 500));
        }

        documentMapper.updateById(document);
        currentJob.setStatus(docStatus.name());
        currentJob.setChunkCount(chunkCount);
        currentJob.setErrorMessage(docStatus == DocumentStatus.FAILED ? truncate(callback.getMessage(), 1000) : null);
        currentJob.setCompletedAt(LocalDateTime.now());
        documentIndexJobMapper.updateById(currentJob);
        // 用量账本：完成按实际分块数结算，失败退回预占。
        // 回调线程无登录上下文，按文档归属租户解析后结算/退回。
        if (docStatus == DocumentStatus.COMPLETED) {
            indexChunkLedger.settle(document, currentJob, chunkCount);
        } else if (docStatus == DocumentStatus.FAILED) {
            indexChunkLedger.release(document, currentJob);
        }
        log.info("文档状态已更新: {} -> {}", documentId, docStatus);
    }

    private DocumentChunk toDocumentChunk(
            Document document, DocumentIndexJob job, DocumentChunkCallbackDTO callbackChunk) {
        if (callbackChunk.getChunkId() == null || callbackChunk.getChunkId().isBlank()) {
            throw new BusinessException("索引回调包含空 chunkId");
        }
        DocumentChunk chunk = new DocumentChunk();
        chunk.setChunkId(callbackChunk.getChunkId());
        chunk.setDocumentId(document.getId());
        chunk.setKnowledgeBaseId(document.getKnowledgeBaseId());
        chunk.setIndexVersion(job.getIndexVersion());
        chunk.setChunkIndex(callbackChunk.getIndex());
        chunk.setBlockType(callbackChunk.getBlockType());
        chunk.setOutlinePath(toJson(callbackChunk.getOutlinePath()));
        chunk.setContentExcerpt(truncate(callbackChunk.getContentExcerpt(), 1000));
        chunk.setCharCount(callbackChunk.getCharCount());
        chunk.setMetadata(toJson(callbackChunk.getMetadata()));
        chunk.setEmbeddingModel(callbackChunk.getEmbeddingModel());
        chunk.setEmbeddingDimension(callbackChunk.getEmbeddingDimension());
        chunk.setEmbeddingVersion(callbackChunk.getEmbeddingVersion());
        return chunk;
    }

    private Long resolveDocumentTenantById(Long documentId) {
        return TenantContext.runAsSystem(() -> {
            Document document = documentMapper.selectById(documentId);
            return document == null ? null : indexChunkLedger.resolveDocumentTenant(document);
        });
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Collections.emptyMap() : value);
        } catch (JsonProcessingException e) {
            throw new BusinessException("无法保存分块元数据");
        }
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return null;
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
