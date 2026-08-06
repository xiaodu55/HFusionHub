package com.hfusionhub.service.impl;

import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * INDEX_CHUNKS 用量账本（预占/结算/退回生命周期，自 VectorizationServiceImpl
 * 收口，第二十五批 God class 拆分）。
 *
 * <p>预占键 {@code INDEX_CHUNKS:<indexVersion>} 贯穿 reserve→settle/release
 * 三方，键格式必须单点维护——编排侧（发起/恢复/对账）与回调侧（完成结算/失败
 * 退回）共用本组件，任何一侧各自持副本都会导致账本悬挂预占。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
class IndexChunkLedger {

    private final UsageLedgerService usageLedgerService;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;

    @Value("${vectorization.bytes-per-chunk-estimate:300}")
    private long bytesPerChunkEstimate;

    /** 发起索引时按文件大小估算预占量（幂等键 INDEX_CHUNKS:&lt;indexVersion&gt;）。 */
    void reserve(Document document, DocumentIndexJob job) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引预占", document.getId());
            return;
        }
        long estimate = estimateIndexChunks(document);
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.reserve(
                    UsageMeter.INDEX_CHUNKS,
                    indexReservationKey(job.getIndexVersion()),
                    estimate,
                    "document_index",
                    String.valueOf(document.getId()));
            return null;
        });
    }

    /** 索引完成按实际分块数结算。 */
    void settle(Document document, DocumentIndexJob job, int actualChunks) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引结算", document.getId());
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.settle(
                    UsageMeter.INDEX_CHUNKS,
                    indexReservationKey(job.getIndexVersion()),
                    Math.max(actualChunks, 0),
                    "document_index",
                    String.valueOf(document.getId()));
            return null;
        });
    }

    /** 发起失败/恢复耗尽/索引失败时退回预占。 */
    void release(Document document, DocumentIndexJob job) {
        Long tenantId = resolveDocumentTenant(document);
        if (tenantId == null) {
            log.warn("无法解析文档 {} 的租户，跳过索引退回", document.getId());
            return;
        }
        TenantContext.runAs(tenantId, () -> {
            usageLedgerService.release(UsageMeter.INDEX_CHUNKS, indexReservationKey(job.getIndexVersion()));
            return null;
        });
    }

    /**
     * 按文件大小估算分块数上界（向上取整）。文件大小未知时退回到一个
     * 保守默认值，保证预占量 > 0（usage_ledger 对 amount <= 0 直接忽略）。
     * 使用 ceil 避免整数除法低估预占（如 301 bytes / 300 = 2 而非 1），
     * 防止索引越过额度门槛。
     */
    private long estimateIndexChunks(Document document) {
        Long fileSize = document.getFileSize();
        if (fileSize == null || fileSize <= 0) {
            return 100L;
        }
        long chunkBytes = Math.max(bytesPerChunkEstimate, 1);
        long estimate = (fileSize + chunkBytes - 1) / chunkBytes;
        return Math.max(1L, estimate);
    }

    private String indexReservationKey(String indexVersion) {
        return "INDEX_CHUNKS:" + indexVersion;
    }

    /**
     * 按文档归属租户解析。回调/恢复线程没有登录上下文，
     * 需经 document → knowledgeBase → user 解析 tenantId。
     * 包级可见：VectorizationCallbackService 的回调租户引导复用同源实现。
     */
    Long resolveDocumentTenant(Document document) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(document.getKnowledgeBaseId());
        if (knowledgeBase == null || knowledgeBase.getUserId() == null) {
            return null;
        }
        User owner = userMapper.selectById(knowledgeBase.getUserId());
        return owner != null ? owner.getTenantId() : null;
    }
}
