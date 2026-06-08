package com.hfusionhub.tenant;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.hfusionhub.config.MybatisPlusConfig;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.ibatis.logging.stdout.StdOutImpl;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.springframework.jdbc.datasource.SimpleDriverDataSource;

import javax.sql.DataSource;
import java.sql.Driver;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 租户行拦截器真实链路集成测试（R15-22）。
 *
 * <p>常规测试跑 H2 + 关闭租户拦截器——核心隔离机制从未被测试覆盖。
 * 本测试起真实 MySQL，跑完整 Flyway 迁移链（V1..V74），用生产
 * {@link MybatisPlusConfig} 的拦截器装配 MyBatis-Plus，验证：</p>
 * <ol>
 *   <li>租户 A 插入的数据对租户 B 不可见（行拦截器 SQL 注入生效）</li>
 *   <li>系统作用域（runAsSystem）跨租户可见</li>
 * </ol>
 *
 * <p>数据源二选一：
 * <ul>
 *   <li>设置 {@code HFH_IT_JDBC_URL}（+ 可选 {@code HFH_IT_JDBC_USER}/
 *       {@code HFH_IT_JDBC_PASS}）使用外部 MySQL（如本地 mysql8 容器，
 *       需先建空库 hfusionhub_it）——Windows 上 Testcontainers 与新版
 *       Docker Desktop 的管道探测不兼容时用这条路径本地验证；</li>
 *   <li>否则使用 Testcontainers 启动 mysql:8.0（CI Linux 正常路径），
 *       无 Docker 时整体跳过。</li>
 * </ul></p>
 *
 * <p>运行方式：{@code mvn test -Pitest -Dtest=TenantInterceptorIsolationIT}</p>
 */
class TenantInterceptorIsolationIT {

    static final String JDBC_URL = System.getenv("HFH_IT_JDBC_URL");
    static final String JDBC_USER = System.getenv().getOrDefault("HFH_IT_JDBC_USER", "itest");
    static final String JDBC_PASS = System.getenv().getOrDefault("HFH_IT_JDBC_PASS", "itest");
    static final boolean USE_EXTERNAL_MYSQL = JDBC_URL != null && !JDBC_URL.isBlank();

    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0")
            .withDatabaseName("hfusionhub_it")
            .withUsername("itest")
            .withPassword("itest");

    private static SqlSessionFactory sqlSessionFactory;

    @BeforeAll
    static void setUpAll() throws Exception {
        if (!USE_EXTERNAL_MYSQL) {
            // Testcontainers 路径：无 Docker 环境（本地 Windows 管道兼容问题
            // 或 CI 无 docker）时跳过而不是失败
            try {
                MYSQL.start();
            } catch (IllegalStateException | org.testcontainers.containers.ContainerLaunchException e) {
                org.junit.jupiter.api.Assumptions.assumeTrue(false, "Docker unavailable: " + e.getMessage());
            }
        }
        DataSource dataSource = dataSource();
        Flyway.configure()
                .dataSource(dataSource)
                .locations("classpath:db/migration")
                .load()
                .migrate();

        // 手动装配：@Value 不会注入，显式开启租户拦截器（生产由
        // hfusionhub.tenant.enabled 驱动，默认 true）
        MybatisPlusConfig mybatisPlusConfig = new MybatisPlusConfig();
        org.springframework.test.util.ReflectionTestUtils
                .setField(mybatisPlusConfig, "tenantEnabled", true);
        MybatisPlusInterceptor interceptor = mybatisPlusConfig.mybatisPlusInterceptor();

        MybatisConfiguration configuration = new MybatisConfiguration();
        configuration.setLogImpl(StdOutImpl.class);
        configuration.setEnvironment(new Environment(
                "itest", new JdbcTransactionFactory(), dataSource));
        configuration.addInterceptor(interceptor);
        // 注册 mapper（MybatisMapperRegistry 在 addMapper 时注册 TableInfo 元数据）
        configuration.addMapper(KnowledgeBaseMapper.class);
        sqlSessionFactory = new org.apache.ibatis.session.SqlSessionFactoryBuilder()
                .build(configuration);

        seedTestUser(dataSource());
    }

    /** knowledge_base.user_id 有 FK 指向 sys_user——补一个最小种子用户（id=1）。 */
    private static void seedTestUser(DataSource dataSource) throws Exception {
        try (var conn = dataSource.getConnection();
             var ps = conn.prepareStatement(
                     "INSERT INTO sys_user (id, username, password, tenant_id) "
                             + "SELECT 1, 'it-seed-user', 'it-noop-password', 1 FROM DUAL "
                             + "WHERE NOT EXISTS (SELECT 1 FROM sys_user WHERE id = 1)")) {
            ps.executeUpdate();
        }
    }

    private static DataSource dataSource() {
        try {
            SimpleDriverDataSource ds = new SimpleDriverDataSource();
            if (USE_EXTERNAL_MYSQL) {
                ds.setDriverClass((Class<? extends Driver>) Class.forName("com.mysql.cj.jdbc.Driver"));
                ds.setUrl(JDBC_URL);
                ds.setUsername(JDBC_USER);
                ds.setPassword(JDBC_PASS);
            } else {
                ds.setDriverClass((Class<? extends Driver>) Class.forName(MYSQL.getDriverClassName()));
                ds.setUrl(MYSQL.getJdbcUrl());
                ds.setUsername(MYSQL.getUsername());
                ds.setPassword(MYSQL.getPassword());
            }
            return ds;
        } catch (ClassNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @AfterAll
    static void tearDownAll() {
        TenantContext.clear();
        if (MYSQL != null && MYSQL.isRunning()) {
            MYSQL.stop();
        }
    }

    private static long insertKb(SqlSession session, String name) {
        KnowledgeBaseMapper mapper = session.getMapper(KnowledgeBaseMapper.class);
        KnowledgeBase kb = new KnowledgeBase();
        kb.setName(name);
        kb.setDescription("it");
        // 手动装配无 MetaObjectHandler（生产由 FieldFill.INSERT 填充），显式给值
        kb.setCreatedAt(java.time.LocalDateTime.now());
        kb.setUpdatedAt(java.time.LocalDateTime.now());
        kb.setDeleted(0);
        // user_id NOT NULL：生产由业务层（当前用户）填写；tenant_id 由行拦截器注入
        kb.setUserId(1L);
        mapper.insert(kb);
        return kb.getId();
    }

    @Test
    void tenantADataIsInvisibleToTenantB() {
        try (SqlSession session = sqlSessionFactory.openSession(true)) {
            KnowledgeBaseMapper mapper = session.getMapper(KnowledgeBaseMapper.class);

            TenantContext.setTenantId(101L);
            long kbA = insertKb(session, "tenant-101-kb");

            TenantContext.setTenantId(202L);
            long kbB = insertKb(session, "tenant-202-kb");

            // 租户 202 只能看到自己的库
            List<KnowledgeBase> visibleToB = mapper.selectList(null);
            assertTrue(visibleToB.stream().allMatch(kb -> kb.getId() == kbB),
                    "租户 202 不得看到租户 101 的知识库");
            assertTrue(visibleToB.stream().anyMatch(kb -> kb.getId() == kbB));

            // 租户 101 只能看到自己的库
            TenantContext.setTenantId(101L);
            List<KnowledgeBase> visibleToA = mapper.selectList(null);
            assertTrue(visibleToA.stream().allMatch(kb -> kb.getId() == kbA),
                    "租户 101 不得看到租户 202 的知识库");

            // 系统作用域跨租户可见
            List<KnowledgeBase> systemVisible = TenantContext.runAsSystem(
                    () -> mapper.selectList(null));
            assertTrue(systemVisible.stream().anyMatch(kb -> kb.getId() == kbA)
                    && systemVisible.stream().anyMatch(kb -> kb.getId() == kbB),
                    "系统作用域应跨租户可见");
        }
    }

    @Test
    void systemScopeQuerySeesAllTenants() {
        try (SqlSession session = sqlSessionFactory.openSession(true)) {
            KnowledgeBaseMapper mapper = session.getMapper(KnowledgeBaseMapper.class);
            TenantContext.setTenantId(301L);
            long kb = insertKb(session, "tenant-301-kb");

            TenantContext.clear();
            Integer count = TenantContext.runAsSystem(() -> {
                List<KnowledgeBase> all = mapper.selectList(
                        new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<KnowledgeBase>()
                                .eq(KnowledgeBase::getId, kb));
                return all.size();
            });
            assertEquals(1, count);
        }
    }
}
