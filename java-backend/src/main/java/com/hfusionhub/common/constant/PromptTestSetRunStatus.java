package com.hfusionhub.common.constant;

import java.util.Set;

/**
 * 提示词测试用例集批量运行的异步任务状态机。
 *
 * <p>生命周期：pending → running → succeeded | failed | cancelled。
 * 该状态由后台 Worker 驱动，支持排队、实时进度、取消与失败重试。
 */
public final class PromptTestSetRunStatus {

    public static final String PENDING = "pending";
    public static final String RUNNING = "running";
    public static final String SUCCEEDED = "succeeded";
    public static final String FAILED = "failed";
    public static final String CANCELLED = "cancelled";

    /** 终态集合：到达后不再执行，可通过 retry 重新排队。 */
    public static final Set<String> TERMINAL_STATUSES = Set.of(SUCCEEDED, FAILED, CANCELLED);

    private PromptTestSetRunStatus() {
    }
}
