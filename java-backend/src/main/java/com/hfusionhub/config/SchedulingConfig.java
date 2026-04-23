package com.hfusionhub.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 定时任务配置 — 仅在非测试环境启用，避免后台调度器在 H2 测试中产生噪声。
 */
@Configuration
@EnableScheduling
@Profile("!test")
public class SchedulingConfig {}
