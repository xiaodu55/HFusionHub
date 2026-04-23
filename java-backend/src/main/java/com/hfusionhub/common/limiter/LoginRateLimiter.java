package com.hfusionhub.common.limiter;

import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.RedisUtils;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * Redis-based login rate limiter.
 *
 * <p>Tracks failed login attempts per IP address.  After {@value #MAX_ATTEMPTS}
 * failures within {@value #WINDOW_SECONDS} seconds the IP is locked out for
 * {@value #LOCKOUT_SECONDS} seconds.  A successful login clears the counter.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LoginRateLimiter {

    private final RedisUtils redisUtils;

    /** Maximum failed attempts before lockout. */
    static final int MAX_ATTEMPTS = 5;

    /** Sliding window for counting failures (seconds). */
    static final long WINDOW_SECONDS = 900; // 15 minutes

    /** Lockout duration after exceeding max attempts (seconds). */
    static final long LOCKOUT_SECONDS = 900; // 15 minutes

    private String attemptKey(String ip) {
        return CommonConstants.REDIS_LIMIT_PREFIX + "attempt:" + ip;
    }

    private String lockoutKey(String ip) {
        return CommonConstants.REDIS_LIMIT_PREFIX + "lockout:" + ip;
    }

    /**
     * Returns {@code true} if the IP is currently locked out.
     */
    public boolean isBlocked(String ip) {
        return redisUtils.hasKey(lockoutKey(ip));
    }

    /**
     * Throws {@link BusinessException} with HTTP 429 if the IP is blocked.
     */
    public void checkBlocked(String ip) {
        if (isBlocked(ip)) {
            log.warn("LOGIN_RATE_LIMIT_BLOCKED ip={}", ip);
            throw new BusinessException(StatusCode.TOO_MANY_REQUESTS, "请求过于频繁，请15分钟后重试");
        }
    }

    /**
     * Record a failed login attempt for the given IP.
     * Locks out the IP if the threshold is exceeded.
     */
    public void recordFailedAttempt(String ip) {
        String key = attemptKey(ip);
        long attempts = redisUtils.increment(key, 1);
        if (attempts == 1) {
            redisUtils.expire(key, WINDOW_SECONDS, TimeUnit.SECONDS);
        }

        if (attempts >= MAX_ATTEMPTS) {
            String lockKey = lockoutKey(ip);
            redisUtils.set(lockKey, String.valueOf(System.currentTimeMillis()), LOCKOUT_SECONDS, TimeUnit.SECONDS);
            log.warn("LOGIN_RATE_LIMIT_LOCKED_OUT ip={} attempts={}", ip, attempts);
        }
    }

    /**
     * Clear failed attempt counter after a successful login.
     */
    public void recordSuccess(String ip) {
        redisUtils.delete(attemptKey(ip));
    }
}
