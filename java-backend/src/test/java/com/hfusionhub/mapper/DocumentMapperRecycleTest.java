package com.hfusionhub.mapper;

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
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
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

/**
 * Verify DocumentMapper.selectExpiredRecycled against H2 —
 * only deleted + expired documents are returned.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
@Transactional
class DocumentMapperRecycleTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @Autowired
    private DocumentMapper documentMapper;

    @Autowired
    private com.hfusionhub.mapper.KnowledgeBaseMapper knowledgeBaseMapper;

    @Autowired
    private com.hfusionhub.mapper.UserMapper userMapper;

    private Long kbId;

    @BeforeEach
    void setUp() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        User user = new User();
        user.setUsername("dmr-" + System.nanoTime());
        user.setPassword("test");
        user.setNickname("DMR");
        user.setStatus(0);
        userMapper.insert(user);
        StpUtil.login(user.getId());

        KnowledgeBase kb = new KnowledgeBase();
        kb.setName("dmr-kb-" + System.nanoTime());
        kb.setUserId(user.getId());
        kb.setStatus(0);
        knowledgeBaseMapper.insert(kb);
        kbId = kb.getId();
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    @Test
    void selectExpiredRecycledReturnsOnlyExpiredDeletedDocuments() {
        LocalDateTime now = LocalDateTime.now();

        // ── Expired: deleted=1, recycle_expires_at in the past → should appear ──
        Document expired = new Document();
        expired.setKnowledgeBaseId(kbId);
        expired.setTitle("expired-doc");
        expired.setDeleted(1);
        expired.setRecycledAt(now.minusDays(8));
        expired.setRecycleExpiresAt(now.minusHours(1));
        expired.setStatus(0);
        documentMapper.insert(expired);

        // ── Not yet expired: deleted=1, recycle_expires_at in the future → should NOT appear ──
        Document future = new Document();
        future.setKnowledgeBaseId(kbId);
        future.setTitle("future-doc");
        future.setDeleted(1);
        future.setRecycledAt(now);
        future.setRecycleExpiresAt(now.plusHours(1));
        future.setStatus(0);
        documentMapper.insert(future);

        // ── Not deleted: deleted=0, even with past expires → should NOT appear ──
        Document notDeleted = new Document();
        notDeleted.setKnowledgeBaseId(kbId);
        notDeleted.setTitle("not-deleted-doc");
        notDeleted.setDeleted(0);
        notDeleted.setRecycledAt(now.minusDays(8));
        notDeleted.setRecycleExpiresAt(now.minusHours(1));
        notDeleted.setStatus(2);
        documentMapper.insert(notDeleted);

        // ── Null expires: deleted=1, recycle_expires_at IS NULL → should NOT appear ──
        Document nullExpires = new Document();
        nullExpires.setKnowledgeBaseId(kbId);
        nullExpires.setTitle("null-expires-doc");
        nullExpires.setDeleted(1);
        nullExpires.setRecycledAt(now.minusDays(8));
        nullExpires.setRecycleExpiresAt(null);
        nullExpires.setStatus(0);
        documentMapper.insert(nullExpires);

        // ── Execute ──
        List<Document> result = documentMapper.selectExpiredRecycled(100);

        // ── Verify: exactly 1 result, the expired doc ──
        assertEquals(1, result.size(), "Only the expired deleted document should be returned");
        assertEquals(expired.getId(), result.get(0).getId());
        assertEquals("expired-doc", result.get(0).getTitle());
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
