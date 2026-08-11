package com.hfusionhub.support;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.containers.ContainerLaunchException;

/**
 * 集成测试基类（C1）：真实 MySQL + 完整 Flyway 迁移链（V1..V84）。
 *
 * <p>携带 {@code @SpringBootTest(NONE)} 与 {@code @ActiveProfiles("it")}，
 * 子类只写业务断言。数据源二选一：</p>
 * <ul>
 *   <li>{@code HFH_IT_JDBC_URL}（+ 可选 {@code HFH_IT_JDBC_USER}/
 *       {@code HFH_IT_JDBC_PASS}）指向外部 MySQL 的空库（如本地 mysql8
 *       容器里的 {@code hfusionhub_it}）——Windows 上 Testcontainers 与
 *       新版 Docker Desktop 管道探测不兼容时用这条路径；</li>
 *   <li>否则尝试 Testcontainers 启动 mysql:8.0（CI Linux 正常路径）。</li>
 *   <li>两者皆不可用时整类跳过（不失败）。</li>
 * </ul>
 *
 * <p>Redis 与 test profile 一致保持 bean 级 mock（子类各自的
 * {@code @MockBean}），不在此启用真实 Redis。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("it")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public abstract class AbstractItMySQLTest {

    static final String EXT_URL = System.getenv("HFH_IT_JDBC_URL");
    static final String EXT_USER = System.getenv().getOrDefault("HFH_IT_JDBC_USER", "itest");
    static final String EXT_PASS = System.getenv().getOrDefault("HFH_IT_JDBC_PASS", "itest");
    static final boolean USE_EXTERNAL_MYSQL = EXT_URL != null && !EXT_URL.isBlank();

    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0")
            .withDatabaseName("hfusionhub_it")
            .withUsername("itest")
            .withPassword("itest");

    /** 容器就绪标志：Testcontainers 路径启动成功后为 true。 */
    static volatile boolean containerReady;

    static {
        if (!USE_EXTERNAL_MYSQL) {
            try {
                MYSQL.start();
                containerReady = true;
            } catch (IllegalStateException | ContainerLaunchException e) {
                // 无可用 Docker：留给 @BeforeAll 的 assume 跳过（不失败）
                System.err.println("[IT] Testcontainers unavailable, integration tests will be skipped: "
                        + e.getMessage());
            }
        }
    }

    @BeforeAll
    static void assumeEnvironmentAvailable() {
        Assumptions.assumeTrue(USE_EXTERNAL_MYSQL || containerReady,
                "真实 MySQL 不可用（未配置 HFH_IT_JDBC_URL 且 Docker/Testcontainers 不可用）");
    }

    @org.springframework.beans.factory.annotation.Autowired
    protected JdbcTemplate jdbcTemplate;

    @BeforeAll
    void resetDatabaseStateOncePerClass() {
        // 非 static：上下文已就绪。每类一次清空——类间隔离、类内保序
        // （有序的有状态套件依赖类内先后状态）。
        // 所有 it 类共享同一个 Spring 上下文与数据库：每个测试前把业务表
        // 全部清空（FK 免检 + TRUNCATE 重置自增），再重播核心种子，
        // 从结构上消除跨类数据污染。flyway_schema_history 保留。
        List<String> tables = jdbcTemplate.queryForList(
                "SELECT table_name FROM information_schema.tables "
                        + "WHERE table_schema = DATABASE() "
                        + "AND table_name <> 'flyway_schema_history' "
                        + "AND table_name <> 'role_permission'",
                String.class);
        jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 0");
        try {
            for (String table : tables) {
                jdbcTemplate.update("TRUNCATE TABLE " + table);
            }
            // 核心种子（与 data-it.sql 一致）：测试主体的 FK 目标
            jdbcTemplate.update("INSERT INTO tenant (id, name, slug, plan_tier, status) VALUES "
                    + "(1, 'Default', 'default', 'enterprise', 'active') "
                    + "ON DUPLICATE KEY UPDATE slug = 'default'");
            jdbcTemplate.update("INSERT INTO sys_user (id, username, password, nickname, role, status, tenant_id) "
                    + "VALUES (1, 'default-user', 'test', 'Default', 'user', 0, 1) "
                    + "ON DUPLICATE KEY UPDATE nickname = 'Default'");
            jdbcTemplate.update("INSERT INTO sys_user (id, username, password, nickname, role, status, tenant_id) "
                    + "VALUES (2, 'it-user', 'test', 'IT User', 'user', 0, 1) "
                    + "ON DUPLICATE KEY UPDATE nickname = 'IT User'");
        } finally {
            jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 1");
        }
        // 生产语义由 TenantContextInterceptor 在 HTTP 层设置租户上下文；
        // 集成测试在这里等价设置（租户 1），拦截器据此盖章 tenant_id
        com.hfusionhub.tenant.TenantContext.setTenantId(1L);
    }

    @BeforeEach
    void setUpTenantContext() {
        com.hfusionhub.tenant.TenantContext.setTenantId(1L);
    }

    @AfterEach
    void clearTenantContext() {
        com.hfusionhub.tenant.TenantContext.clear();
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        if (USE_EXTERNAL_MYSQL) {
            registry.add("spring.datasource.url", () -> EXT_URL);
            registry.add("spring.datasource.username", () -> EXT_USER);
            registry.add("spring.datasource.password", () -> EXT_PASS);
        } else {
            registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
            registry.add("spring.datasource.username", MYSQL::getUsername);
            registry.add("spring.datasource.password", MYSQL::getPassword);
        }
    }
}
