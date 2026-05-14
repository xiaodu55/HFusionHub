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
}
