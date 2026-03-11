package com.hfusionhub.service;

import com.hfusionhub.common.constant.AgentConstants;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.Set;

/**
 * Agent 重试策略 — 纯逻辑组件（无 Mapper 依赖），可独立单元测试。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AgentRetryPolicy {

    @Value("${agent.retry.max-attempts:3}")
    private int maxAttempts;

    @Value("${agent.retry.base-delay-seconds:30}")
    private long baseDelaySeconds;

    @Value("${agent.retry.backoff-multiplier:2}")
    private int backoffMultiplier;

    @Value("${agent.retry.max-delay-seconds:600}")
    private long maxDelaySeconds;

    @Value("${agent.retry.retryable-error-codes:timeout,execution_timeout,connection_error,tool_error,internal_error}")
    private String retryableErrorCodesConfig;

    private volatile Set<String> parsedRetryableCodes;

    /**
     * 判断错误码是否可重试
     */
    public boolean isRetryable(String errorCode) {
        return AgentConstants.isRetryableErrorCode(errorCode, getRetryableErrorCodes());
    }

    /**
     * 计算下一次执行计划时间（指数退避）
     *
     * @param attemptNumber 当前尝试次数（1-based）
     * @return 计划执行时间
     */
    public LocalDateTime computeNextScheduledAt(int attemptNumber) {
        return LocalDateTime.now().plusSeconds(backoffSeconds(attemptNumber));
    }

    /**
     * 计算退避秒数
     *
     * @param attemptNumber 当前尝试次数（1-based）
     * @return 退避秒数
     */
    public long backoffSeconds(int attemptNumber) {
        if (attemptNumber <= 1) return 0;
        // baseDelay * multiplier^(attemptNumber - 2), capped at maxDelay
        // attempt 2 = baseDelay, attempt 3 = baseDelay * multiplier, etc.
        long delay = baseDelaySeconds;
        for (int i = 2; i < attemptNumber; i++) {
            delay *= backoffMultiplier;
            if (delay >= maxDelaySeconds) {
                return maxDelaySeconds;
            }
        }
        return Math.min(delay, maxDelaySeconds);
    }

    /**
     * 判断是否应进入死信
     *
     * @param attemptNumber 当前尝试次数（1-based）
     * @return true=应进入死信
     */
    public boolean shouldDeadLetter(int attemptNumber) {
        return attemptNumber >= maxAttempts;
    }

    /**
     * 获取最大尝试次数
     */
    public int getMaxAttempts() {
        return maxAttempts;
    }

    /**
     * 获取最大派发次数（孤儿重派上限）
     */
    @Value("${agent.retry.max-dispatch-count:3}")
    private int maxDispatchCount;

    public int getMaxDispatchCount() {
        return maxDispatchCount;
    }

    /**
     * 解析配置的可重试错误码（惰性缓存）
     */
    private Set<String> getRetryableErrorCodes() {
        if (parsedRetryableCodes != null) return parsedRetryableCodes;
        synchronized (this) {
            if (parsedRetryableCodes != null) return parsedRetryableCodes;
            if (retryableErrorCodesConfig == null || retryableErrorCodesConfig.isBlank()) {
                parsedRetryableCodes = AgentConstants.DEFAULT_RETRYABLE_ERROR_CODES;
            } else {
                parsedRetryableCodes = Set.of(retryableErrorCodesConfig.trim().split("\\s*,\\s*"));
            }
        }
        return parsedRetryableCodes;
    }
}
