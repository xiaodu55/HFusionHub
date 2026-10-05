package com.hfusionhub.mapper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.Document;
import com.hfusionhub.support.AbstractItMySQLTest;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 第九十六批：写侧时钟口径的判据（真实 MySQL）。
 *
 * <p>库里 DATETIME 存的是**字面墙钟**，谁写进去就用谁的钟：Java 侧用 JVM 默认钟
 * （{@code LocalDateTime.now()}），谓词里用 {@code NOW()} 则是**会话时区**的钟。
 * 两者都没有被任何一处声明钉住，于是同一行的"是否过期"取决于连接恰好落在哪个会话、
 * 进程恰好跑在哪个时区。本类把三件事钉成断言：</p>
 * <ol>
 *   <li>回收站过期判定（{@code DocumentMapper.selectExpiredRecycled}）不随会话时区翻转；</li>
 *   <li>待审批列表（{@code AgentApprovalMapper.selectPendingByUserId}）同上；</li>
 *   <li>过期清扫（{@code AgentApprovalMapper.selectExpiredPending}）只认库的 UTC 钟。红判据
 *       阶段它收的是调用方传入的 {@code now}（{@code AgentTaskServiceImpl} 给的是 JVM 的
 *       {@code LocalDateTime.now()}），于是"哪些审批过期"随进程默认时区翻转，与列表侧的 DB 钟
 *       判定构成双钟；修复把该入参删掉后，这条断言退化为"清扫不随会话时区翻转"。</li>
 * </ol>
 *
 * <p>行值一律按**库里读到的 UTC 时刻**自校准（{@code UNIX_TIMESTAMP(UTC_TIMESTAMP())}），
 * 不取宿主时钟，所以判据与跑它的机器时区无关；时间戳以字符串字面量写入，绕开驱动的类型
 * 转换，使"列里到底存了什么"没有第三种解释。</p>
 *
 * <p>用例落在 {@code (UTC 此刻, UTC 此刻+8h)} 这个窗口里——这是会话为 UTC 时会判
 * "未过期"、会话为 +08:00 时用 {@code NOW()} 会判"过期"的唯一区间（偏移 8 小时）。
 * 每个用例同时插一行"8 小时前就该过期"的对照并断言它必须被选中：少了这条，
 * "两个会话下都不出现"也会被读成"两个会话下一致"，判据就在假绿上宣称修好了。</p>
 *
 * <p>{@code SET time_zone} 确实命中了 mapper 所用的连接：用例事务内 {@code CONNECTION_ID()}
 * 不变、{@code TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW())} 为 28800，换参数后的 mapper 读
 * 会随之翻转（第九十六批用临时诊断量过）。但**同参数**的第二次读会被 MyBatis 一级缓存兜住、
 * 根本不去问库——第一版判据正是栽在这里：两条会话免疫用例在缺陷面前都是绿的。那是一次
 * 真实的假绿，成因已被 {@code identicalStatementAndParamsAreServedFromTheMyBatisFirstLevelCache}
 * 钉成用例，其余用例因此要么换参数读，要么（清扫那条已无参数可换）显式清缓存后用
 * "刚插入的行必须可见"自证这次读真的问了库。</p>
 *
 * <p>本类不断言"JVM 默认钟 == 库钟"——那由部署面声明（compose/helm 的
 * {@code JAVA_TOOL_OPTIONS=-Duser.timezone=UTC}）与文本门禁负责。把它写成断言就等于
 * 要求每个开发机的操作系统时区都是 UTC，正是第九十四批刚从 {@code application-it.yml}
 * 撤掉的那类宿主假设。</p>
 */
@Transactional
class WriteClockCaliberTest extends AbstractItMySQLTest {

    private static final DateTimeFormatter LITERAL = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final String ZONE_UTC = "'+00:00'";
    private static final String ZONE_PLUS8 = "'+08:00'";
    private static final String ZONE_DEFAULT = "DEFAULT";
    private static final long EIGHT_HOURS = 8 * 3600L;
    private static final long USER_ID = 1L;
    private static final long OTHER_USER_ID = 2L;

    // it profile 排除了 Redis 自动配置，与其余 IT 类一样按 bean 级 mock 补齐
    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @Autowired
    private DocumentMapper documentMapper;

    @Autowired
    private AgentApprovalMapper approvalMapper;

    /** 与本类 mapper 共用同一个事务内 SqlSession，用于显式清掉它的一级缓存。 */
    @Autowired
    private org.mybatis.spring.SqlSessionTemplate sqlSession;

    /**
     * 夹具完整性守卫：{@code SET time_zone} 是会话变量，不随 {@code @Transactional} 回滚，
     * 而连接归还给 Hikari 后会被下一个类复用。泄漏一次就会污染整条 IT 套件，
     * 所以每个用例开始前先确认会话没有偏移。
     */
    @BeforeEach
    void assertSessionZoneIsUnshifted() {
        assertEquals("SYSTEM", sessionZone(), "会话时区泄漏自上一个用例，本类的判据不可信");
    }

    private String sessionZone() {
        return jdbcTemplate.queryForObject("SELECT @@session.time_zone", String.class);
    }

    private void useZone(String quotedOffset) {
        jdbcTemplate.execute("SET time_zone = " + quotedOffset);
    }

    /** 库里 UTC 此刻 + offsetSeconds 的字面墙钟（与宿主时区无关）。 */
    private String literalAtUtcNow(long offsetSeconds) {
        long utcNow = jdbcTemplate.queryForObject("SELECT UNIX_TIMESTAMP(UTC_TIMESTAMP())", Long.class);
        return LocalDateTime.ofEpochSecond(utcNow + offsetSeconds, 0, ZoneOffset.UTC)
                .format(LITERAL);
    }

    private long insertRecycledDocument(String expiresLiteral) {
        // knowledge_base/user 不在本用例的关注面上，FK 免检后只写过谓词要读的列；
        // 与 AbstractItMySQLTest 的清理路径同一手法。
        jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 0");
        try {
            jdbcTemplate.update(
                    "INSERT INTO document (knowledge_base_id, tenant_id, title, status, deleted,"
                            + " recycled_at, recycle_expires_at) VALUES (1, 1, ?, 0, 1, ?, ?)",
                    "b96-recycled",
                    expiresLiteral,
                    expiresLiteral);
        } finally {
            jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 1");
        }
        return jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
    }

    private String insertPendingApproval(long userId, String expiresLiteral) {
        // approval_id 列是 VARCHAR(36)，恰好放一个 UUID，加前缀就溢出
        String approvalId = java.util.UUID.randomUUID().toString();
        jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 0");
        try {
            jdbcTemplate.update(
                    "INSERT INTO agent_approval (approval_id, task_id, run_id, user_id, tenant_id,"
                            + " tool_name, tool_input_hash, arguments_summary, status, expires_at)"
                            + " VALUES (?, 1, 1, ?, 1, 'b96-tool', 'hash', 'summary', 'pending', ?)",
                    approvalId,
                    userId,
                    expiresLiteral);
        } finally {
            jdbcTemplate.execute("SET FOREIGN_KEY_CHECKS = 1");
        }
        return approvalId;
    }

    private static java.util.Set<Long> docIds(List<Document> docs) {
        return docs.stream().map(Document::getId).collect(java.util.stream.Collectors.toSet());
    }

    private static java.util.Set<String> idsOf(List<AgentApproval> approvals) {
        return approvals.stream().map(AgentApproval::getApprovalId).collect(java.util.stream.Collectors.toSet());
    }

    @Test
    void recycleExpiryVerdictDoesNotDependOnSessionZone() {
        long futureDocId = insertRecycledDocument(literalAtUtcNow(EIGHT_HOURS / 2));
        // 对照组：8 小时前就该过期的行。没有它，"两个会话下都不出现"也会被当成
        // "判定与会话无关"而绿——那正是假绿的形状。
        long pastDocId = insertRecycledDocument(literalAtUtcNow(-EIGHT_HOURS));

        java.util.Set<Long> underUtc;
        java.util.Set<Long> underPlus8;
        try {
            useZone(ZONE_UTC);
            // 两次读故意换 limit：MyBatis 的一级缓存以 {语句+参数} 为键活在本用例的事务里，
            // 同参二次读根本不问库（见下面那条专门的用例）。
            underUtc = docIds(documentMapper.selectExpiredRecycled(100));
            useZone(ZONE_PLUS8);
            underPlus8 = docIds(documentMapper.selectExpiredRecycled(101));
        } finally {
            useZone(ZONE_DEFAULT);
        }

        assertTrue(underUtc.contains(pastDocId), "对照行（8 小时前已过期）在 UTC 会话下没被选中：本类夹具与谓词没有接上，判据不可信");
        assertTrue(underPlus8.contains(pastDocId), "对照行（8 小时前已过期）在 +08:00 会话下没被选中：判据不可信");
        assertFalse(underUtc.contains(futureDocId), "四个小时后才过期的行，在 UTC 会话下不该被判过期");
        assertEquals(
                underUtc.contains(futureDocId),
                underPlus8.contains(futureDocId),
                () -> "同一行的过期判定随会话时区翻转（UTC=" + underUtc.contains(futureDocId) + " / +08:00="
                        + underPlus8.contains(futureDocId) + "）：谓词里的 NOW() 取的是会话钟，而列里存的是另一套墙钟");
    }

    @Test
    void pendingApprovalListDoesNotDependOnSessionZone() {
        // 两个用户各插一对（未过期/已过期），UTC 会话查用户 1、+08:00 会话查用户 2：
        // 参数不同 ⇒ 两次读都真的问库（同参会命中一级缓存），而两行的时间形状完全一样，
        // 所以"两侧模式相同"就是会话免疫。
        String futureForUser1 = insertPendingApproval(USER_ID, literalAtUtcNow(EIGHT_HOURS / 2));
        String pastForUser1 = insertPendingApproval(USER_ID, literalAtUtcNow(-EIGHT_HOURS));
        String futureForUser2 = insertPendingApproval(OTHER_USER_ID, literalAtUtcNow(EIGHT_HOURS / 2));
        String pastForUser2 = insertPendingApproval(OTHER_USER_ID, literalAtUtcNow(-EIGHT_HOURS));

        java.util.Set<String> underUtc;
        java.util.Set<String> underPlus8;
        try {
            useZone(ZONE_UTC);
            underUtc = idsOf(approvalMapper.selectPendingByUserId(USER_ID));
            useZone(ZONE_PLUS8);
            underPlus8 = idsOf(approvalMapper.selectPendingByUserId(OTHER_USER_ID));
        } finally {
            useZone(ZONE_DEFAULT);
        }

        assertTrue(underUtc.contains(futureForUser1), "UTC 会话下未过期的待审批没出现在列表里：夹具没接上");
        assertFalse(underUtc.contains(pastForUser1), "UTC 会话下已过期的审批不该出现在待办列表里");
        assertTrue(
                underPlus8.contains(futureForUser2), "会话挪到 +08:00 后，未过期的待审批从列表里消失：expires_at > NOW() 里的 NOW() 取的是会话钟");
        assertFalse(underPlus8.contains(pastForUser2), "+08:00 会话下已过期的审批同样不该出现（这一条同时证明这次读真的问了库）");
    }

    /**
     * 过期清扫只剩一把钟（库的 UTC 钟）：谓词用 {@code UTC_TIMESTAMP()}，会话挪不动它。
     *
     * <p>这条语句没有参数，"换参数才真的问库"在这里用不上，所以先显式清掉本事务 SqlSession
     * 的一级缓存，再插一行刚过期的：它在 {@code +08:00} 那次读里必须可见。看不见就说明那次读
     * 没问库，下面的免疫断言是空的——于是这条本身判红，而不是留下一个静默的假绿。</p>
     */
    @Test
    void expirySweepDoesNotDependOnSessionZone() {
        String futureApprovalId = insertPendingApproval(USER_ID, literalAtUtcNow(EIGHT_HOURS / 2));
        String pastApprovalId = insertPendingApproval(USER_ID, literalAtUtcNow(-EIGHT_HOURS));

        java.util.Set<String> underUtc;
        java.util.Set<String> underPlus8;
        try {
            useZone(ZONE_UTC);
            underUtc = idsOf(approvalMapper.selectExpiredPending());

            sqlSession.clearCache();
            String freshExpiredId = insertPendingApproval(OTHER_USER_ID, literalAtUtcNow(-60));
            useZone(ZONE_PLUS8);
            underPlus8 = idsOf(approvalMapper.selectExpiredPending());
            assertTrue(underPlus8.contains(freshExpiredId), "+08:00 那次清扫读没有真的问库（刚插入的行不可见），本用例的会话免疫断言不成立");
        } finally {
            useZone(ZONE_DEFAULT);
        }

        assertTrue(underUtc.contains(pastApprovalId), "对照行（8 小时前已过期）没被 UTC 会话扫到：夹具与谓词没接上");
        assertTrue(underPlus8.contains(pastApprovalId), "对照行在 +08:00 会话下同样应被扫到");
        assertFalse(underUtc.contains(futureApprovalId), "行在四小时后才过期，UTC 会话下不该被扫到");
        assertEquals(
                underUtc.contains(futureApprovalId),
                underPlus8.contains(futureApprovalId),
                () -> "过期清扫的结论随会话时区翻转（UTC=" + underUtc.contains(futureApprovalId) + " / +08:00="
                        + underPlus8.contains(futureApprovalId) + "）：谓词读的是会话钟 NOW()，而 expires_at 里存的是另一套墙钟");
    }

    /**
     * 本类为什么每次读都要换参数——把原因钉成用例，而不是只写在注释里。
     *
     * <p>MyBatis 的一级缓存活在一个 SqlSession 里，而 Spring 测试的事务让整条用例共用一个
     * SqlSession。同一条语句 + 同一组参数的第二次读不会再去库里，返回的是第一次的结果集。
     * 于是"切会话时区后再读一次"根本不会反映切换：本类的会话免疫判据在缺陷存在时也会绿。
     * 这条用例与钟无关（用"新插入的行看不看得见"当探针），所以修完时钟口径后仍然成立。</p>
     */
    @Test
    void identicalStatementAndParamsAreServedFromTheMyBatisFirstLevelCache() {
        long earlyDocId = insertRecycledDocument(literalAtUtcNow(-EIGHT_HOURS));
        useZone(ZONE_UTC);
        try {
            assertTrue(docIds(documentMapper.selectExpiredRecycled(100)).contains(earlyDocId), "第一行对照就该被选中");

            long lateDocId = insertRecycledDocument(literalAtUtcNow(-EIGHT_HOURS * 2));

            java.util.Set<Long> sameParams = docIds(documentMapper.selectExpiredRecycled(100));
            assertFalse(
                    sameParams.contains(lateDocId),
                    "同参二次读本该命中一级缓存（看不到新插的行）；若这条红了，说明缓存作用域变了，" + "本类其余用例'换参数才真的问库'的前提也要重新核");

            java.util.Set<Long> otherParams = docIds(documentMapper.selectExpiredRecycled(101));
            assertTrue(otherParams.contains(lateDocId), "换参数才真的问库：新行应当可见");
        } finally {
            useZone(ZONE_DEFAULT);
        }
    }
}
