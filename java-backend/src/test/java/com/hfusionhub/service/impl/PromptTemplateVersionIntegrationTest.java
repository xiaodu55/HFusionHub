package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaTokenContextModelBox;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.support.AbstractItMySQLTest;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * End-to-end persistence test against H2: create → edit twice →
 * publish → unpublish → rollback.  Uses a real MyBatis-Plus mapper
 * stack; mocks only Redis (not needed for prompt templates).
 */
@Transactional
class PromptTemplateVersionIntegrationTest extends AbstractItMySQLTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @Autowired
    private PromptTemplateServiceImpl service;

    @Autowired
    private UserMapper userMapper;

    private Long userId;

    @BeforeEach
    void setUp() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        User user = new User();
        user.setTenantId(1L); // sys_user 在租户拦截器忽略表中，需显式盖章
        user.setUsername("pt-int-" + System.nanoTime());
        user.setPassword("test");
        user.setNickname("PT");
        user.setStatus(0);
        userMapper.insert(user);
        userId = user.getId();

        StpUtil.login(userId);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    @Test
    void createThenEditTwicePublishUnpublishAndRollback() {
        // ── Create v1 ──
        PromptTemplateInfoDTO v1 = service.create(save("助手", "V1内容。"));
        assertEquals(1, v1.getVersion());
        assertEquals("DRAFT", v1.getStatus());

        List<PromptTemplateVersionDTO> vs = service.listVersions(v1.getId());
        assertEquals(1, vs.size());
        assertEquals("CREATE", vs.get(0).getOperation());
        Long v1Id = vs.get(0).getId();

        // ── Edit → v2 ──
        service.update(v1.getId(), save("助手", "V2内容。", 1));
        vs = service.listVersions(v1.getId());
        assertEquals(2, vs.size());
        assertEquals(2, vs.get(0).getVersion());
        assertEquals("EDIT", vs.get(0).getOperation());
        assertEquals(1, vs.get(1).getVersion());
        assertEquals("CREATE", vs.get(1).getOperation());

        // ── Edit → v3 ──
        service.update(v1.getId(), save("助手", "V3内容。", 2));
        vs = service.listVersions(v1.getId());
        assertEquals(3, vs.size(), "create + 2 edits = 3 content snapshots");

        // ── Publish (v3→v4) + Unpublish (v4→v5) ──
        PromptTemplateInfoDTO v4 = service.publish(v1.getId(), 3);
        assertEquals(4, v4.getVersion());
        assertEquals("PUBLISHED", v4.getStatus());
        PromptTemplateInfoDTO v5 = service.unpublish(v1.getId(), 4);
        assertEquals(5, v5.getVersion());
        assertEquals("DRAFT", v5.getStatus());
        vs = service.listVersions(v1.getId());
        assertEquals(5, vs.size(), "3 content + publish + unpublish = 5");

        // ── Rollback to v1 by snapshot ID (v5→v6) ──
        PromptTemplateInfoDTO v6 = service.rollback(v1.getId(), v1Id, 5);
        assertEquals(6, v6.getVersion());
        assertEquals("DRAFT", v6.getStatus());
        assertEquals("V1内容。", v6.getContent());

        vs = service.listVersions(v1.getId());
        assertEquals(6, vs.size());
        assertEquals("ROLLBACK", vs.get(0).getOperation());
        assertEquals(6, vs.get(0).getVersion());

        // ── No duplicate version per content op ──
        Map<Integer, Integer> dup = new HashMap<>();
        for (var sv : vs) {
            if (List.of("CREATE", "EDIT", "ROLLBACK").contains(sv.getOperation())) {
                dup.merge(sv.getVersion(), 1, Integer::sum);
            }
        }
        for (var e : dup.entrySet()) {
            assertEquals(1, e.getValue().intValue(), "v" + e.getKey() + " dup content snapshot count=" + e.getValue());
        }
    }

    @Test
    void concurrentUpdateSecondWriterIsRejected() {
        // ── Create v1 ──
        PromptTemplateInfoDTO v1 = service.create(save("并发模板", "V1-原始内容。"));
        assertEquals(1, v1.getVersion());

        // ── First writer (expectedVersion=1 matches DB) → succeeds, version → 2 ──
        PromptTemplateInfoDTO v2 = service.update(v1.getId(), save("并发模板", "V2-第一个写入者。", 1));
        assertEquals(2, v2.getVersion());
        assertEquals("V2-第一个写入者。", v2.getContent());

        // ── Second writer (still holds expectedVersion=1, but DB is now at 2) → REJECTED ──
        BusinessException ex = assertThrows(
                BusinessException.class, () -> service.update(v1.getId(), save("并发模板", "V2-第二个写入者（应被拒绝）。", 1)));
        assertTrue(ex.getMessage().contains("已被其他操作更新"), "Expected version-conflict message, got: " + ex.getMessage());
        assertTrue(
                ex.getMessage().contains("v2"),
                "Expected message to mention current version v2, got: " + ex.getMessage());
        assertEquals(409, ex.getCode());

        // ── DB still contains first writer's content, not overwritten ──
        PromptTemplateInfoDTO current = service.listMine().stream()
                .filter(t -> t.getId().equals(v1.getId()))
                .findFirst()
                .orElseThrow();
        assertEquals(2, current.getVersion());
        assertEquals("V2-第一个写入者。", current.getContent());

        // Only 3 snapshots: CREATE(v1) + EDIT(v2) — second writer never persisted
        List<PromptTemplateVersionDTO> vs = service.listVersions(v1.getId());
        assertEquals(2, vs.size());
    }

    @Test
    void concurrentPublishAfterEditIsRejected() {
        // ── Create v1 ──
        PromptTemplateInfoDTO v1 = service.create(save("发布冲突", "V1-内容。"));
        assertEquals(1, v1.getVersion());
        assertEquals("DRAFT", v1.getStatus());

        // ── Someone edits → v2 ──
        service.update(v1.getId(), save("发布冲突", "V2-被编辑过。", 1));

        // ── Stale publish (expectedVersion=1, but DB is now v2) → REJECTED ──
        BusinessException ex = assertThrows(BusinessException.class, () -> service.publish(v1.getId(), 1));
        assertTrue(ex.getMessage().contains("已被其他操作更新"), "Expected version-conflict message");
        assertEquals(409, ex.getCode());

        // Template is still DRAFT (publish was rejected)
        PromptTemplateInfoDTO current = service.listMine().stream()
                .filter(t -> t.getId().equals(v1.getId()))
                .findFirst()
                .orElseThrow();
        assertEquals("DRAFT", current.getStatus());
        assertEquals(2, current.getVersion());
        assertEquals("V2-被编辑过。", current.getContent());
    }

    @Test
    void concurrentPublishAndUnpublishOnlyOneSucceeds() {
        // ── Create v1 ──
        PromptTemplateInfoDTO v1 = service.create(save("发布撤回并发", "V1-内容。"));
        assertEquals(1, v1.getVersion());
        assertEquals("DRAFT", v1.getStatus());

        // ── First operation: publish with expectedVersion=1 → succeeds, version increments to 2 ──
        PromptTemplateInfoDTO v2 = service.publish(v1.getId(), 1);
        assertEquals(2, v2.getVersion());
        assertEquals("PUBLISHED", v2.getStatus());

        // ── Second operation: unpublish with expectedVersion=1 (stale!) → REJECTED ──
        BusinessException ex = assertThrows(BusinessException.class, () -> service.unpublish(v1.getId(), 1));
        assertTrue(ex.getMessage().contains("已被其他操作更新"), "Expected version-conflict message, got: " + ex.getMessage());
        assertTrue(ex.getMessage().contains("v2"), "Expected message to mention current version v2");
        assertEquals(409, ex.getCode());

        // ── DB still PUBLISHED (unpublish was rejected) ──
        PromptTemplateInfoDTO current = service.listMine().stream()
                .filter(t -> t.getId().equals(v1.getId()))
                .findFirst()
                .orElseThrow();
        assertEquals("PUBLISHED", current.getStatus());
        assertEquals(2, current.getVersion());

        // Only 2 snapshots: CREATE(v1) + PUBLISH(v2) — unpublish never persisted
        List<PromptTemplateVersionDTO> vs = service.listVersions(v1.getId());
        assertEquals(2, vs.size());
    }

    @Test
    void updateRejectsWhenExpectedVersionMissing() {
        // ── Create v1 ──
        PromptTemplateInfoDTO v1 = service.create(save("缺版本号", "V1-内容。"));
        assertEquals(1, v1.getVersion());

        // ── Update without expectedVersion → REJECTED ──
        BusinessException ex = assertThrows(
                BusinessException.class, () -> service.update(v1.getId(), save("缺版本号", "新内容"))); // null expectedVersion
        assertTrue(
                ex.getMessage().contains("expectedVersion"),
                "Expected error about missing expectedVersion, got: " + ex.getMessage());

        // ── DB unchanged ──
        PromptTemplateInfoDTO current = service.listMine().stream()
                .filter(t -> t.getId().equals(v1.getId()))
                .findFirst()
                .orElseThrow();
        assertEquals(1, current.getVersion());
        assertEquals("V1-内容。", current.getContent());
    }

    private PromptTemplateSaveDTO save(String name, String content) {
        return save(name, content, null);
    }

    private PromptTemplateSaveDTO save(String name, String content, Integer expectedVersion) {
        PromptTemplateSaveDTO dto = new PromptTemplateSaveDTO();
        dto.setName(name);
        dto.setContent(content);
        dto.setExpectedVersion(expectedVersion);
        return dto;
    }

    private static class MockSaTokenContext implements SaTokenContext {

        private final Map<String, Object> storage = new HashMap<>();

        private SaTokenContextModelBox modelBox;

    

        private MockSaTokenContext() {

            // 构造即装配 modelBox：SaManager.setSaTokenContext 之后立即可用

            setContext(mock(SaRequest.class), mock(SaResponse.class), new SaStorage() {

                @Override

                public Object getSource() {

                    return storage;

                }

    

                @Override

                public Object get(String key) {

                    return storage.get(key);

                }

    

                @Override

                public SaStorage set(String key, Object value) {

                    storage.put(key, value);

                    return this;

                }

    

                @Override

                public SaStorage delete(String key) {

                    storage.remove(key);

                    return this;

                }

            });

        }

    

        @Override

        public void setContext(SaRequest request, SaResponse response, SaStorage storage) {

            this.modelBox = new SaTokenContextModelBox(request, response, storage);

        }

    

        @Override

        public void clearContext() {

            this.modelBox = null;

        }

    

        @Override

        public boolean isValid() {

            return this.modelBox != null;

        }

    

        @Override

        public SaTokenContextModelBox getModelBox() {

            return this.modelBox;

        }

    }
}
