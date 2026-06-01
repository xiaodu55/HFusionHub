package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.FeatureFlagService;
import com.hfusionhub.service.TenantPlanBindingService;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 投标套餐模块开关单元测试（招投标垂直化 · P2-2）
 *
 * <p>规则：模块可用 = 套餐授权 AND 平台 FeatureFlag 开关。</p>
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidPlanGateServiceImplTest {

    @Mock private TenantPlanBindingService bindingService;
    @Mock private FeatureFlagService featureFlagService;

    private BidPlanGateService service;

    @BeforeEach
    void setUp() {
        service = new BidPlanGateServiceImpl(bindingService, featureFlagService);
    }

    @Test
    void moduleDisabledWhenNotGrantedByPlan() {
        when(bindingService.hasModule(7L, "draft")).thenReturn(false);

        assertFalse(service.isModuleEnabled(7L, "draft"));
        // 未授权则不再求值 FeatureFlag
        verify(featureFlagService, never()).isEnabled(anyString(), any(), any(), any(), any());
    }

    @Test
    void moduleDisabledWhenFlagOff() {
        when(bindingService.hasModule(7L, "draft")).thenReturn(true);
        when(featureFlagService.isEnabled(anyString(), any(), any(), any(), any())).thenReturn(false);

        assertFalse(service.isModuleEnabled(7L, "draft"));
    }

    @Test
    void moduleEnabledWhenGrantedAndFlagOn() {
        when(bindingService.hasModule(7L, "draft")).thenReturn(true);
        when(featureFlagService.isEnabled(anyString(), any(), any(), any(), any())).thenReturn(true);

        assertTrue(service.isModuleEnabled(7L, "draft"));
    }

    @Test
    void unknownModuleKeyRejected() {
        assertFalse(service.isModuleEnabled(7L, "nonexistent"));
        verify(bindingService, never()).hasModule(any(), any());
    }

    @Test
    void requireModuleThrowsForbiddenWhenDisabled() {
        when(bindingService.hasModule(7L, "check")).thenReturn(false);

        BusinessException ex = assertThrows(
                BusinessException.class, () -> service.requireModule(7L, "check", "废标自检"));

        assertEquals(StatusCode.FORBIDDEN, ex.getCode());
        assertTrue(ex.getMessage().contains("废标自检"));
        assertTrue(ex.getMessage().contains("套餐中心"));
    }

    @Test
    void requireModulePassesWhenEnabled() {
        when(bindingService.hasModule(7L, "draft")).thenReturn(true);
        when(featureFlagService.isEnabled(anyString(), any(), any(), any(), any())).thenReturn(true);

        service.requireModule(7L, "draft", "标书撰写"); // 不抛异常即通过
    }

    @Test
    void moduleStatusMapsAllModuleKeys() {
        when(bindingService.hasModule(any(), any())).thenAnswer(inv -> "draft".equals(inv.getArgument(1)));
        when(featureFlagService.isEnabled(anyString(), any(), any(), any(), any())).thenReturn(true);

        Map<String, Boolean> status = service.moduleStatus(7L);

        assertEquals(4, status.size());
        assertTrue(status.get("draft"));
        assertFalse(status.get("check"));
        assertFalse(status.get("docx"));
        assertFalse(status.get("openapi"));
    }
}
