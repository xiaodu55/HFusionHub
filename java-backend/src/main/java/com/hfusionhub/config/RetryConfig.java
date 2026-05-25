package com.hfusionhub.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.retry.annotation.EnableRetry;

/**
 * Spring Retry 配置
 *
 * <p>启用 {@code @Retryable} 注解支持，为同步 AI 服务调用提供自动重试能力。</p>
 *
 * <p>重试策略：
 * <ul>
 *   <li>目标异常：{@code ResourceAccessException}（网络连接失败）、
 *       {@code HttpServerErrorException}（5xx 服务器错误）</li>
 *   <li>最大重试次数：3 次（含首次调用共 4 次尝试）</li>
 *   <li>退避策略：指数退避，初始 1s，倍率 2，最大 10s</li>
 * </ul>
 * </p>
 *
 * <p>注意：
 * <ul>
 *   <li>流式请求（SSE）不适用重试 — WebClient 的 Reactor 链由调用方控制取消与重连</li>
 *   <li>4xx 客户端错误（如认证失败、参数错误）不重试，直接抛出</li>
 * </ul>
 * </p>
 *
 * @author HFusionHub Team
 */
@Configuration
@EnableRetry
public class RetryConfig {}
