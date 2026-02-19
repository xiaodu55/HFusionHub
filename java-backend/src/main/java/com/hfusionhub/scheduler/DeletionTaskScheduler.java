package com.hfusionhub.scheduler;

import com.hfusionhub.entity.DeletionTask;
import com.hfusionhub.service.DeletionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 删除任务调度器 — 每30秒处理待执行和可重试的删除任务
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class DeletionTaskScheduler {

    private final DeletionService deletionService;

    @Scheduled(fixedDelay = 30_000)
    public void processPendingTasks() {
        List<DeletionTask> tasks = deletionService.getPendingTasks();
        if (tasks.isEmpty()) return;

        log.debug("处理 {} 个待处理删除任务", tasks.size());
        for (DeletionTask task : tasks) {
            try {
                deletionService.executeStep(task);
            } catch (Exception e) {
                log.error("删除任务执行异常: taskId={}, step={}", task.getId(), task.getStepIndex(), e);
                deletionService.markFailed(task, e.getMessage());
            }
        }
    }
}
