package com.hfusionhub.scheduler;

import com.hfusionhub.entity.DeletionTask;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.tenant.TenantContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DeletionTaskSchedulerTest {

    @AfterEach
    void clearTenant() {
        TenantContext.clear();
    }

    @Test
    void completesPendingStepsInOneScheduledRun() {
        DeletionService deletionService = mock(DeletionService.class);
        DeletionTask task = new DeletionTask();
        task.setStatus("PENDING");
        when(deletionService.getPendingTasks()).thenReturn(List.of(task));
        doAnswer(invocation -> {
            assertTrue(TenantContext.isSystemScope());
            if (task.getStepIndex() == null) {
                task.setStepIndex(1);
            } else {
                task.setStatus("COMPLETED");
            }
            return null;
        }).when(deletionService).executeStep(task);

        new DeletionTaskScheduler(deletionService).processPendingTasks();

        verify(deletionService, times(2)).executeStep(task);
    }
}
