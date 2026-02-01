package com.hfusionhub.common.utils;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

/**
 * Redis 工具类
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RedisUtils {

    private final StringRedisTemplate redisTemplate;

    /**
     * 设置缓存
     *
     * @param key   键
     * @param value 值
     */
    public void set(String key, String value) {
        redisTemplate.opsForValue().set(key, value);
    }

    /**
     * 设置缓存（带过期时间）
     *
     * @param key     键
     * @param value   值
     * @param timeout 过期时间
     * @param unit    时间单位
     */
    public void set(String key, String value, long timeout, TimeUnit unit) {
        redisTemplate.opsForValue().set(key, value, timeout, unit);
    }

    /**
     * 获取缓存
     *
     * @param key 键
     * @return 值
     */
    public String get(String key) {
        return redisTemplate.opsForValue().get(key);
    }

    /**
     * 删除缓存
     *
     * @param key 键
     * @return 是否删除成功
     */
    public Boolean delete(String key) {
        return redisTemplate.delete(key);
    }

    /**
     * 判断缓存是否存在
     *
     * @param key 键
     * @return 是否存在
     */
    public Boolean hasKey(String key) {
        return redisTemplate.hasKey(key);
    }

    /**
     * 设置缓存过期时间
     *
     * @param key     键
     * @param timeout 过期时间
     * @param unit    时间单位
     * @return 是否设置成功
     */
    public Boolean expire(String key, long timeout, TimeUnit unit) {
        return redisTemplate.expire(key, timeout, unit);
    }

    /**
     * 获取缓存过期时间
     *
     * @param key 键
     * @return 过期时间
     */
    public Long getExpire(String key) {
        return redisTemplate.getExpire(key);
    }

    /**
     * 自增
     *
     * @param key   键
     * @param delta 增量
     * @return 自增后的值
     */
    public Long increment(String key, long delta) {
        return redisTemplate.opsForValue().increment(key, delta);
    }

    /**
     * 自减
     *
     * @param key   键
     * @param delta 减量
     * @return 自减后的值
     */
    public Long decrement(String key, long delta) {
        return redisTemplate.opsForValue().increment(key, -delta);
    }

    /**
     * 设置缓存（秒）
     *
     * @param key     键
     * @param value   值
     * @param seconds 过期秒数
     */
    public void setSeconds(String key, String value, long seconds) {
        set(key, value, seconds, TimeUnit.SECONDS);
    }

    /**
     * 设置缓存（分钟）
     *
     * @param key     键
     * @param value   值
     * @param minutes 过期分钟数
     */
    public void setMinutes(String key, String value, long minutes) {
        set(key, value, minutes, TimeUnit.MINUTES);
    }

    /**
     * 设置缓存（小时）
     *
     * @param key    键
     * @param value  值
     * @param hours  过期小时数
     */
    public void setHours(String key, String value, long hours) {
        set(key, value, hours, TimeUnit.HOURS);
    }

    /**
     * 设置缓存（天）
     *
     * @param key   键
     * @param value 值
     * @param days  过期天数
     */
    public void setDays(String key, String value, long days) {
        set(key, value, days, TimeUnit.DAYS);
    }
}
