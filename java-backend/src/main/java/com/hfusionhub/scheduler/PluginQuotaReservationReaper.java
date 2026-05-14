package com.hfusionhub.scheduler;

import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.entity.UsageReservation;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Releases plugin reservations whose Python terminal callback was lost.
 *
 * <p>Plugin executions are bounded by the sandbox timeout; a five-minute
 * default keeps the user-facing quota fail-closed during a transient outage
 * while preventing an unrecoverable reservation leak. Agent reservations use
 * the durable queue recovery path and are intentionally not handled here.</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PluginQuotaReservationReaper {

    private static final int BATCH_SIZE = 100;

    private final UsageReservationMapper reservationMapper;
    private final UsageLedgerService usageLedgerService;

    @Value("${hfusionhub.quota.plugin-reservation-timeout-seconds:300}")
    private long pluginReservationTimeoutSeconds;

    @SchedulerLock("plugin-quota-reservation-reaper")
    @Scheduled(fixedDelayString = "${hfusionhub.quota.plugin-reservation-reaper-ms:60000}")
    public void releaseStaleReservations() {
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(pluginReservationTimeoutSeconds);
        List<UsageReservation> stale = TenantContext.runAsSystem(
                () -> reservationMapper.selectStalePluginReservations(staleBefore, BATCH_SIZE));
        int released = 0;
        for (UsageReservation reservation : stale) {
            try {
                TenantContext.runAs(
                        reservation.getTenantId(),
                        () -> usageLedgerService.release(UsageMeter.PLUGIN_EXECUTIONS, reservation.getRequestId()));
                released++;
            } catch (Exception e) {
                log.warn(
                        "Failed to release stale plugin reservation id={} requestId={}: {}",
                        reservation.getId(),
                        reservation.getRequestId(),
                        e.getMessage());
            }
        }
        if (released > 0) {
            log.warn("Released {} stale plugin quota reservations", released);
        }
    }
}
