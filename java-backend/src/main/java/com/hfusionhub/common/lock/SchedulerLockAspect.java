package com.hfusionhub.common.lock;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

/**
 * {@link SchedulerLock} 注解切面 — 通过 Redis SETNX 实现跨实例互斥。
 *
 * <p>Redis 不可用时的行为可配置（{@code hfusionhub.scheduler-lock.fail-open}，默认
 * {@code false} 即 fail-closed）：fail-closed 时本次调度直接跳过，任务延迟到
 * Redis 恢复后的下一个周期，杜绝多实例在无锁状态下并发执行；清理/补偿类任务
 * 均按周期幂等设计，延迟执行是安全的。如需旧版"无锁也执行"的行为，将
 * {@code SCHEDULER_LOCK_FAIL_OPEN} 设为 {@code true}。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Aspect
@Component
@RequiredArgsConstructor
public class SchedulerLockAspect {

    private static final String LOCK_KEY_PREFIX = "scheduler:lock:";

    /** Lua 原子 compare-and-delete：仅当 key 仍持有本实例 token 时删除，防止误删其它实例续得的锁 */
    private static final DefaultRedisScript<Long> UNLOCK_SCRIPT = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            Long.class);

    private final StringRedisTemplate redisTemplate;

    /** Redis 故障时是否退化为无锁执行；默认 false（fail-closed，跳过本次调度） */
    @Value("${hfusionhub.scheduler-lock.fail-open:false}")
    private boolean failOpen;

    @Around("@annotation(schedulerLock)")
    public Object around(ProceedingJoinPoint joinPoint, SchedulerLock schedulerLock) throws Throwable {
        String key = LOCK_KEY_PREFIX + schedulerLock.value();
        String token = UUID.randomUUID().toString();
        boolean locked = false;
        try {
            Boolean acquired =
                    redisTemplate.opsForValue().setIfAbsent(key, token, schedulerLock.ttlSeconds(), TimeUnit.SECONDS);
            if (Boolean.TRUE.equals(acquired)) {
                locked = true;
                log.trace("Scheduler lock '{}' acquired by this instance", schedulerLock.value());
            } else {
                log.debug("Scheduler lock '{}' held by another instance, skipping execution", schedulerLock.value());
                return null;
            }
        } catch (Exception e) {
            if (failOpen) {
                // Redis 不可用 → fail-open，退化为无锁执行（历史行为，可配置回退）
                log.warn(
                        "Scheduler lock '{}' unavailable (Redis error), executing without lock: {}",
                        schedulerLock.value(),
                        e.getMessage());
                return joinPoint.proceed();
            }
            // 默认 fail-closed：跳过本次调度，任务由下一个周期补偿
            log.warn(
                    "Scheduler lock '{}' unavailable (Redis error), skipping this round (fail-closed): {}",
                    schedulerLock.value(),
                    e.getMessage());
            return null;
        }

        try {
            return joinPoint.proceed();
        } finally {
            if (locked) {
                try {
                    redisTemplate.execute(UNLOCK_SCRIPT, List.of(key), token);
                } catch (Exception e) {
                    // 锁随 TTL 兜底过期，无需阻塞任务执行
                    log.warn("Failed to release scheduler lock '{}', it will expire after TTL", schedulerLock.value());
                }
            }
        }
    }
}
