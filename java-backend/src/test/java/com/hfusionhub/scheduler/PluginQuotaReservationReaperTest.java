package com.hfusionhub.scheduler;

import com.hfusionhub.entity.UsageReservation;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PluginQuotaReservationReaperTest {

    @AfterEach
    void clearTenant() {
        TenantContext.clear();
    }

    @Test
    void releasesEachStalePluginReservationInItsOriginalTenant() {
        UsageReservationMapper mapper = mock(UsageReservationMapper.class);
        UsageLedgerService ledger = mock(UsageLedgerService.class);
        PluginQuotaReservationReaper reaper = new PluginQuotaReservationReaper(mapper, ledger);
        ReflectionTestUtils.setField(reaper, "pluginReservationTimeoutSeconds", 300L);

        UsageReservation reservation = new UsageReservation();
        reservation.setId(3L);
        reservation.setTenantId(11L);
        reservation.setRequestId("plugin:run-1:attempt-1");
        when(mapper.selectStalePluginReservations(any(), eq(100))).thenReturn(List.of(reservation));
        doAnswer(invocation -> {
            assertEquals(11L, TenantContext.requireTenantId());
            return null;
        }).when(ledger).release(any(), anyString());

        reaper.releaseStaleReservations();

        verify(ledger).release(UsageMeter.PLUGIN_EXECUTIONS, "plugin:run-1:attempt-1");
    }

    @Test
    void continuesReapingOtherReservationsAfterOneFailure() {
        UsageReservationMapper mapper = mock(UsageReservationMapper.class);
        UsageLedgerService ledger = mock(UsageLedgerService.class);
        PluginQuotaReservationReaper reaper = new PluginQuotaReservationReaper(mapper, ledger);

        UsageReservation failed = reservation(1L, 11L, "plugin:failed");
        UsageReservation next = reservation(2L, 12L, "plugin:next");
        when(mapper.selectStalePluginReservations(any(), eq(100))).thenReturn(List.of(failed, next));
        doThrow(new IllegalStateException("temporary database failure"))
                .when(ledger).release(UsageMeter.PLUGIN_EXECUTIONS, "plugin:failed");

        reaper.releaseStaleReservations();

        verify(ledger).release(UsageMeter.PLUGIN_EXECUTIONS, "plugin:next");
    }

    private static UsageReservation reservation(Long id, Long tenantId, String requestId) {
        UsageReservation reservation = new UsageReservation();
        reservation.setId(id);
        reservation.setTenantId(tenantId);
        reservation.setRequestId(requestId);
        return reservation;
    }
}
