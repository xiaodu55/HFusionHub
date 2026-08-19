package com.hfusionhub.common.lock;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 分布式调度锁注解 — 防止多实例部署时定时任务重复执行。
 *
 * <p>基于 Redis SETNX（key = {@code scheduler:lock:{name}}，TTL 兜底），
 * 持锁期间运行，结束后按 token 比对删除（Lua 原子 compare-and-delete），
 * 避免误删其它实例续得的锁。</p>
 *
 * <p><b>无自动续期</b>：TTL 必须大于单次任务的最长执行时长——任务超过 TTL
 * 后锁过期，其他实例可能并发进入，任务内部需自行幂等（如按文档行锁串行化）。</p>
 *
 * <p>Redis 不可用时的行为由 {@code hfusionhub.scheduler-lock.fail-open} 配置：
 * 默认 fail-closed（跳过本次执行，避免多实例无锁并发）；置为 true 退化为
 * 无锁直接执行（历史行为）。</p>
 *
 * @author HFusionHub Team
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface SchedulerLock {

    /** 锁名称（同一名称在多个实例间互斥），建议使用调度任务语义名，如 {@code "document-index-recovery"} */
    String value();

    /** 锁 TTL 秒数，必须大于单次任务最长执行时长，作为任务崩溃时的兜底释放 */
    long ttlSeconds() default 300;
}
