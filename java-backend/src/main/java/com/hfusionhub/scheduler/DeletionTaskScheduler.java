package com.hfusionhub.scheduler;

import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.entity.DeletionTask;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.tenant.TenantContext;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 删除任务调度器 — 每30秒处理待执行和可重试的删除任务
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class DeletionTaskScheduler {

    private static final int MAX_STEPS_PER_TASK = 10;

    private final DeletionService deletionService;

    @SchedulerLock("deletion-task")
    @Scheduled(fixedDelay = 30_000)
    public void processPendingTasks() {
        TenantContext.runAsSystem(() -> doProcessPendingTasks());
    }

    private void doProcessPendingTasks() {
        List<DeletionTask> tasks = deletionService.getPendingTasks();
        if (tasks.isEmpty()) return;

        log.debug("处理 {} 个待处理删除任务", tasks.size());
        for (DeletionTask task : tasks) {
            try {
                for (int step = 0; step < MAX_STEPS_PER_TASK; step++) {
                    deletionService.executeStep(task);
                    if (!"PENDING".equals(task.getStatus())) {
                        break;
                    }
                }
            } catch (Exception e) {
                log.error("删除任务执行异常: taskId={}, step={}", task.getId(), task.getStepIndex(), e);
                deletionService.markFailed(task, e.getMessage());
            }
        }
    }
}
