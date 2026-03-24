package com.hfusionhub.service.impl;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

/**
 * End-to-end persistence test against H2: create → edit twice →
 * publish → unpublish → rollback.  Uses a real MyBatis-Plus mapper
 * stack; mocks only Redis (not needed for prompt templates).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Transactional
class PromptTemplateVersionIntegrationTest {

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
        service.update(v1.getId(), save("助手", "V2内容。"));
        vs = service.listVersions(v1.getId());
        assertEquals(2, vs.size());
        assertEquals(2, vs.get(0).getVersion()); assertEquals("EDIT", vs.get(0).getOperation());
        assertEquals(1, vs.get(1).getVersion()); assertEquals("CREATE", vs.get(1).getOperation());

        // ── Edit → v3 ──
        service.update(v1.getId(), save("助手", "V3内容。"));
        vs = service.listVersions(v1.getId());
        assertEquals(3, vs.size(), "create + 2 edits = 3 content snapshots");

        // ── Publish + Unpublish ──
        service.publish(v1.getId());
        service.unpublish(v1.getId());
        vs = service.listVersions(v1.getId());
        assertEquals(5, vs.size(), "3 content + publish + unpublish = 5");

        // ── Rollback to v1 by snapshot ID ──
        PromptTemplateInfoDTO v4 = service.rollback(v1.getId(), v1Id);
        assertEquals(4, v4.getVersion());
        assertEquals("DRAFT", v4.getStatus());
        assertEquals("V1内容。", v4.getContent());

        vs = service.listVersions(v1.getId());
        assertEquals(6, vs.size());
        assertEquals("ROLLBACK", vs.get(0).getOperation());
        assertEquals(4, vs.get(0).getVersion());

        // ── No duplicate version per content op ──
        Map<Integer, Integer> dup = new HashMap<>();
        for (var sv : vs) {
            if (List.of("CREATE", "EDIT", "ROLLBACK").contains(sv.getOperation())) {
                dup.merge(sv.getVersion(), 1, Integer::sum);
            }
        }
        for (var e : dup.entrySet()) {
            assertEquals(1, e.getValue().intValue(),
                    "v" + e.getKey() + " dup content snapshot count=" + e.getValue());
        }
    }

    private PromptTemplateSaveDTO save(String name, String content) {
        PromptTemplateSaveDTO dto = new PromptTemplateSaveDTO();
        dto.setName(name); dto.setContent(content);
        return dto;
    }

    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> store = new HashMap<>();
        @Override public SaRequest getRequest() { return mock(SaRequest.class); }
        @Override public SaResponse getResponse() { return mock(SaResponse.class); }
        @Override public SaStorage getStorage() {
            return new SaStorage() {
                @Override public Object getSource() { return store; }
                @Override public Object get(String k) { return store.get(k); }
                @Override public SaStorage set(String k, Object v) { store.put(k, v); return this; }
                @Override public SaStorage delete(String k) { store.remove(k); return this; }
            };
        }
        @Override public boolean matchPath(String p, String path) { return true; }
        @Override public boolean isValid() { return true; }
    }
}
