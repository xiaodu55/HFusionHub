package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.AppApiKeyInfoDTO;
import com.hfusionhub.dto.AppCreateDTO;
import com.hfusionhub.dto.AppInfoDTO;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.AppApiKey;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.AppApiKeyMapper;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AppServiceImplTest {

    @Mock
    private AppMapper appMapper;

    @Mock
    private AppApiKeyMapper apiKeyMapper;

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    @InjectMocks
    private AppServiceImpl appService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        jwtUtilsMock = mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    private KnowledgeBase ownedKb() {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(10L);
        kb.setUserId(1L);
        return kb;
    }

    private App publishedApp() {
        App app = new App();
        app.setId(1L);
        app.setUserId(1L);
        app.setName("客服助手");
        app.setKnowledgeBaseId(10L);
        app.setStatus(1);
        return app;
    }

    @Test
    void createSetsOwnerTenantAndDefaultStyle() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(ownedKb());
        when(appMapper.insert(any(App.class))).thenReturn(1);

        AppCreateDTO dto = new AppCreateDTO();
        dto.setName("客服助手");
        dto.setKnowledgeBaseId(10L);

        AppInfoDTO result = appService.create(dto);

        assertEquals("客服助手", result.getName());
        assertEquals(10L, result.getKnowledgeBaseId());
        assertEquals("detailed", result.getStyle());
        assertEquals(0, result.getStatus());
        verify(appMapper).insert(any(App.class));
    }

    @Test
    void createRejectsForeignKnowledgeBase() {
        KnowledgeBase foreign = new KnowledgeBase();
        foreign.setId(10L);
        foreign.setUserId(2L); // owned by another user
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(foreign);

        AppCreateDTO dto = new AppCreateDTO();
        dto.setName("x");
        dto.setKnowledgeBaseId(10L);

        assertThrows(BusinessException.class, () -> appService.create(dto));
    }

    @Test
    void publishRequiresBoundKnowledgeBase() {
        App app = new App();
        app.setId(1L);
        app.setUserId(1L);
        app.setKnowledgeBaseId(null);
        when(appMapper.selectById(1L)).thenReturn(app);

        assertThrows(BusinessException.class, () -> appService.publish(1L));
    }

    @Test
    void publishSetsPublishedStatus() {
        when(appMapper.selectById(1L)).thenReturn(publishedApp());

        AppInfoDTO result = appService.publish(1L);

        assertEquals(1, result.getStatus());
        verify(appMapper).updateById(any(App.class));
    }

    @Test
    void createApiKeyRequiresPublishedAppAndReturnsSecretOnce() {
        when(appMapper.selectById(1L)).thenReturn(publishedApp());
        when(apiKeyMapper.insert(any(AppApiKey.class))).thenReturn(1);

        AppApiKeyInfoDTO result = appService.createApiKey(1L, "生产 Key");

        assertNotNull(result.getSecret());
        assertTrue(result.getSecret().startsWith("hf_"));
        assertEquals("hf_", result.getKeyPrefix().substring(0, 3));
        verify(apiKeyMapper).insert(any(AppApiKey.class));
    }

    @Test
    void createApiKeyRejectsDraftApp() {
        App draft = publishedApp();
        draft.setStatus(0);
        when(appMapper.selectById(1L)).thenReturn(draft);

        assertThrows(BusinessException.class, () -> appService.createApiKey(1L, "x"));
    }

    @Test
    void unauthorizedUserCannotAccessApp() {
        when(appMapper.selectById(1L)).thenReturn(publishedApp());
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(2L);

        assertThrows(BusinessException.class, () -> appService.get(1L));
    }
}
