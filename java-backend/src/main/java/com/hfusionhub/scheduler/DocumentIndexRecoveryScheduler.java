package com.hfusionhub.scheduler;

import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.service.VectorizationService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Retries indexing attempts that were abandoned by a Java or Python restart. */
@Slf4j
@Component
@RequiredArgsConstructor
public class DocumentIndexRecoveryScheduler {

    private final VectorizationService vectorizationService;

    @SchedulerLock("document-index-recovery")
    @Scheduled(fixedDelayString = "${rag.index.recovery-delay-ms:300000}")
    public void recoverStaleJobs() {
        int recovered = TenantContext.runAsSystem(() -> vectorizationService.recoverStaleIndexJobs());
        if (recovered > 0) {
            log.info("已恢复 {} 个超时索引任务", recovered);
        }
    }

    /**
     * 向量库对账健康检查：对比 Milvus 实体数与 {@code document_chunk} 表，
     * 失配时显式告警。周期独立于恢复任务（默认 15 分钟），避免每次轮询
     * 都跨租户打 Python。
     */
    @SchedulerLock("vector-store-reconcile")
    @Scheduled(fixedDelayString = "${rag.index.reconcile-delay-ms:900000}")
    public void reconcileVectorStore() {
        int mismatches = TenantContext.runAsSystem(() -> vectorizationService.reconcileVectorCounts());
        if (mismatches > 0) {
            log.error("向量库对账发现 {} 个知识库实体数失配，请检查向量库卷挂载与数据一致性", mismatches);
        }
    }
}
