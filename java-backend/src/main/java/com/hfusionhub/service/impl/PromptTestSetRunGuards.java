package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.hfusionhub.common.constant.PromptTestSetRunStatus;
import com.hfusionhub.entity.PromptTestSetRun;

/**
 * 提示词测试集批量运行的守卫更新构建器。
 *
 * <p>所有 Worker 写入（进度推进、结果持久化、终态收敛、取消）都必须携带
 * 「token + 活跃状态」守卫：仅当 run 仍处于 pending/running 且
 * execution_token 与本次执行捕获的 token 一致时，后续 SET 才会命中 1 行。
 * 旧 Worker（取消→重试后 token 已重新生成）或跨实例已收敛的 run 将命中 0 行，
 * 从而被原子地隔离。
 */
final class PromptTestSetRunGuards {

    private PromptTestSetRunGuards() {}

    static LambdaUpdateWrapper<PromptTestSetRun> activeRunGuard(Long runId, String token) {
        LambdaUpdateWrapper<PromptTestSetRun> wrapper = new LambdaUpdateWrapper<PromptTestSetRun>()
                .eq(PromptTestSetRun::getId, runId)
                .in(PromptTestSetRun::getStatus, PromptTestSetRunStatus.ACTIVE_STATUSES);
        if (token == null) {
            wrapper.isNull(PromptTestSetRun::getExecutionToken);
        } else {
            wrapper.eq(PromptTestSetRun::getExecutionToken, token);
        }
        return wrapper;
    }
}
