package com.hfusionhub.config;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.dao.SaTokenDao;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import jakarta.annotation.PostConstruct;
import org.springframework.boot.test.context.TestConfiguration;

/**
 * Test configuration that replaces the Redis-backed Sa-Token DAO with an
 * in-memory implementation so that tests can run without external Redis.
 *
 * Usage: {@code @Import(TestSaTokenConfig.class)} on any test class that
 * needs to call {@link StpUtil#login(Object)} or {@link StpUtil#checkLogin()}.
 */
@TestConfiguration
public class TestSaTokenConfig {

    /**
     * Replace the global SaTokenDao with an in-memory implementation
     * (ConcurrentHashMap-backed) instead of the Redis-backed default.
     * Runs once per Spring context load.
     */
    @PostConstruct
    public void initSaTokenDao() {
        SaTokenDao inMemoryDao = new SaTokenDaoDefaultImpl();
        SaManager.setSaTokenDao(inMemoryDao);
    }
}
