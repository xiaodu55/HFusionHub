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
 * <p>Redis 不可用时 fail-open（跳过加锁直接执行），保证清理/补偿任务不因 Redis 抖动而中断。</p>
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
