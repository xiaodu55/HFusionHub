package com.hfusionhub.scheduler;

import com.hfusionhub.service.VectorReconciliationService;
import com.hfusionhub.tenant.TenantContext;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Runs periodic read-only reconciliation between MySQL chunks and the vector
 * store, emitting a log line for any drift that is detected.
 *
 * <p>Automatic repair is intentionally not performed here — a failed repair
 * must not silently mutate either store.  Drift is surfaced via logs and the
 * {@code /admin/vector-reconciliation} API for operators.</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class VectorReconciliationScheduler {

    private final VectorReconciliationService reconciliationService;

    @Scheduled(cron = "${vector-reconciliation.cron:0 0 3 * * *}")
    public void runPeriodicReconciliation() {
        Map<String, Object> summary = TenantContext.runAsSystem(reconciliationService::reconcileAll);
        Object healthy = summary.get("healthy");
        long orphans = ((Number) summary.get("total_orphan_vectors")).longValue();
        long missing = ((Number) summary.get("total_missing_vectors")).longValue();
        if (!Boolean.TRUE.equals(healthy)) {
            log.warn(
                    "Vector reconciliation found drift: documents={}, orphan_vectors={}, missing_vectors={}. "
                            + "Run /admin/vector-reconciliation to inspect and repair.",
                    summary.get("total_documents"),
                    orphans,
                    missing);
        } else {
            log.info(
                    "Vector reconciliation OK: documents={}, mysql_chunks={}, orphan_vectors=0, missing_vectors=0.",
                    summary.get("total_documents"),
                    summary.get("total_mysql_chunks"));
        }
    }
}
