package com.hfusionhub.service;

import com.hfusionhub.entity.DeletionTask;

/**
 * 异步删除任务服务
 *
 * @author HFusionHub Team
 */
public interface DeletionService {

    /**
     * 创建删除任务（Outbox）
     *
     * @param taskType KB_DELETE / DOCUMENT_DELETE
     * @param targetId 目标ID
     * @return 创建的任务
     */
    DeletionTask createTask(String taskType, Long targetId);

    /**
     * 执行任务的下一个步骤
     *
     * @param task 删除任务
     */
    void executeStep(DeletionTask task);

    /**
     * 获取待处理的任务列表
     */
    java.util.List<DeletionTask> getPendingTasks();

    /**
     * 标记任务为失败
     */
    void markFailed(DeletionTask task, String errorMessage);
}
