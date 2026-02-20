package com.hfusionhub.config;

import com.hfusionhub.common.limiter.LoginRateLimiter;
import com.hfusionhub.common.utils.IpUtils;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * Interceptor that checks login rate limits <em>before</em> the Sa-Token
 * authentication interceptor runs.  Registered for {@code /user/login} and
 * {@code /user/register} only.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LoginRateLimitInterceptor implements HandlerInterceptor {

    private final LoginRateLimiter rateLimiter;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) {
        String ip = IpUtils.getClientIp(request);
        rateLimiter.checkBlocked(ip);
        return true;
    }
}
