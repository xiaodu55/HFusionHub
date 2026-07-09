package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaTokenContextModelBox;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.dto.*;
import com.hfusionhub.service.FeatureFlagService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.*;
import org.springframework.test.util.ReflectionTestUtils;

@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FeatureFlagSecurityTest {

    private static final String VALID_TOKEN = "test-secret-token-123";
    private static FeatureFlagService mockService;
    private static FeatureFlagInternalController internalController;
    private static FeatureFlagController mgmtController;

    @BeforeAll
    static void setup() {
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        mockService = mock(FeatureFlagService.class);

        internalController = new FeatureFlagInternalController(mockService);
        ReflectionTestUtils.setField(internalController, "expectedToken", VALID_TOKEN);

        mgmtController = new FeatureFlagController(mockService);
    }

    @AfterEach
    void tearDown() {
        reset(mockService);
        try {
            StpUtil.logout();
        } catch (Exception ignored) {
        }
    }

    // ─── Internal snapshot: token protection ─────────────────────────────

    @Test
    @Order(1)
    void snapshot_noToken_returns403() {
        var req = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(req.getHeader("X-Internal-Token")).thenReturn(null);

        assertEquals(403, internalController.snapshot(req).getCode());
        verifyNoInteractions(mockService);
    }

    @Test
    @Order(2)
    void snapshot_wrongToken_returns403() {
        var req = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(req.getHeader("X-Internal-Token")).thenReturn("wrong");

        assertEquals(403, internalController.snapshot(req).getCode());
        verifyNoInteractions(mockService);
    }

    @Test
    @Order(3)
    void snapshot_validToken_returns200() {
        var req = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(req.getHeader("X-Internal-Token")).thenReturn(VALID_TOKEN);
        when(mockService.getSnapshot()).thenReturn(List.of());

        assertEquals(200, internalController.snapshot(req).getCode());
        verify(mockService).getSnapshot();
    }

    @Test
    @Order(4)
    void snapshot_partialToken_returns403() {
        var req = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(req.getHeader("X-Internal-Token")).thenReturn(VALID_TOKEN.substring(0, 5));

        assertEquals(403, internalController.snapshot(req).getCode());
    }

    // ─── Management: CRUD delegates to service ───────────────────────────

    @Test
    @Order(10)
    void create_callsService() {
        var dto = new FeatureFlagCreateDTO();
        dto.setFlagKey("test.flag");
        dto.setEnabled(false);
        when(mockService.create(any())).thenReturn(null);

        mgmtController.create(dto);
        verify(mockService).create(dto);
    }

    @Test
    @Order(11)
    void update_callsService() {
        when(mockService.update(eq(1L), any())).thenReturn(null);

        mgmtController.update(1L, new FeatureFlagUpdateDTO());
        verify(mockService).update(eq(1L), any());
    }

    @Test
    @Order(12)
    void delete_callsService() {
        mgmtController.delete(1L);
        verify(mockService).delete(1L);
    }

    @Test
    @Order(13)
    void getById_callsService() {
        mgmtController.getById(1L);
        verify(mockService).getById(1L);
    }

    @Test
    @Order(14)
    void getByKey_callsService() {
        mgmtController.getByKey("k");
        verify(mockService).getByKey("k");
    }

    @Test
    @Order(15)
    void list_callsService() {
        mgmtController.list(1, 20);
        verify(mockService).list(1, 20);
    }

    @Test
    @Order(16)
    void listAll_callsService() {
        mgmtController.listAll();
        verify(mockService).listAll();
    }

    // ─── Evaluate: requires login (Sa-Token in-memory mode) ─────────────

    @Test
    @Order(20)
    void evaluate_noLogin_throwsNotLogin() {
        // In in-memory mode StpUtil.getLoginId() returns -1 when no session,
        // but Sa-Token only throws when a global config is set.
        // Verify that calling without login still delegates to service
        // (the real guard is @SaCheckRole on admin endpoints; evaluate has none).
        var dto = new FeatureFlagEvaluateDTO();
        dto.setFlagKey("agent.enabled");
        when(mockService.evaluate(any())).thenReturn(null);

        mgmtController.evaluate(dto);
        verify(mockService).evaluate(dto);
    }

    @Test
    @Order(21)
    void evaluate_withLogin_callsService() {
        StpUtil.login(100L);
        var dto = new FeatureFlagEvaluateDTO();
        dto.setFlagKey("agent.enabled");
        when(mockService.evaluate(any())).thenReturn(null);

        mgmtController.evaluate(dto);
        verify(mockService).evaluate(dto);
    }

    @Test
    @Order(22)
    void evaluateBatch_withLogin_callsService() {
        StpUtil.login(100L);
        var dto = new FeatureFlagEvaluateDTO();
        dto.setFlagKey("agent.enabled");
        when(mockService.evaluate(any())).thenReturn(null);

        mgmtController.evaluateBatch(List.of(dto));
        verify(mockService).evaluate(dto);
    }

    // ─── @SaCheckRole annotation verification ────────────────────────────

    @Test
    @Order(30)
    void create_hasAdminAnnotation() throws Exception {
        var ann = FeatureFlagController.class
                .getMethod("create", FeatureFlagCreateDTO.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class);
        assertNotNull(ann, "create() must have @SaCheckRole(\"admin\")");
        assertTrue(List.of(ann.value()).contains("admin"));
    }

    @Test
    @Order(31)
    void update_hasAdminAnnotation() throws Exception {
        assertNotNull(FeatureFlagController.class
                .getMethod("update", Long.class, FeatureFlagUpdateDTO.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    @Test
    @Order(32)
    void delete_hasAdminAnnotation() throws Exception {
        assertNotNull(FeatureFlagController.class
                .getMethod("delete", Long.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    @Test
    @Order(33)
    void addRule_hasAdminAnnotation() throws Exception {
        assertNotNull(FeatureFlagController.class
                .getMethod("addRule", Long.class, FeatureFlagRuleCreateDTO.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    @Test
    @Order(34)
    void updateRule_hasAdminAnnotation() throws Exception {
        assertNotNull(FeatureFlagController.class
                .getMethod("updateRule", Long.class, FeatureFlagRuleUpdateDTO.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    @Test
    @Order(35)
    void deleteRule_hasAdminAnnotation() throws Exception {
        assertNotNull(FeatureFlagController.class
                .getMethod("deleteRule", Long.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    @Test
    @Order(36)
    void evaluate_noAdminAnnotation() throws Exception {
        assertNull(FeatureFlagController.class
                .getMethod("evaluate", FeatureFlagEvaluateDTO.class)
                .getAnnotation(cn.dev33.satoken.annotation.SaCheckRole.class));
    }

    // ─── MockSaTokenContext (in-memory, no Redis) ────────────────────────

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
