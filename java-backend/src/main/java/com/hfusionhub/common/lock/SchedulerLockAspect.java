package com.hfusionhub.common.lock;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

/**
 * {@link SchedulerLock} 注解切面 — 通过 Redis SETNX 实现跨实例互斥。
 *
 * <p>Redis 不可用时 fail-open：加锁失败（异常）时仅告警并直接执行任务，
 * 保证清理/补偿任务不因 Redis 抖动而中断（单实例或 Redis 故障期间退化为无锁执行）。</p>
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

    @Around("@annotation(schedulerLock)")
    public Object around(ProceedingJoinPoint joinPoint, SchedulerLock schedulerLock) throws Throwable {
        String key = LOCK_KEY_PREFIX + schedulerLock.value();
        String token = UUID.randomUUID().toString();
        boolean locked = false;
        try {
            Boolean acquired = redisTemplate
                    .opsForValue()
                    .setIfAbsent(key, token, schedulerLock.ttlSeconds(), TimeUnit.SECONDS);
            if (Boolean.TRUE.equals(acquired)) {
                locked = true;
                log.trace("Scheduler lock '{}' acquired by this instance", schedulerLock.value());
            } else {
                log.debug("Scheduler lock '{}' held by another instance, skipping execution", schedulerLock.value());
                return null;
            }
        } catch (Exception e) {
            // Redis 不可用 → fail-open，退化为无锁执行
            log.warn("Scheduler lock '{}' unavailable (Redis error), executing without lock: {}",
                    schedulerLock.value(), e.getMessage());
            return joinPoint.proceed();
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
