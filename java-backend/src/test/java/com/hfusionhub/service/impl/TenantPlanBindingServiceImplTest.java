package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PlanBindingDTO;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantPlanBinding;
import com.hfusionhub.mapper.BidSubscriptionMapper;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantPlanBindingMapper;
import com.hfusionhub.tenant.TenantContext;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 租户套餐绑定服务单元测试（招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class TenantPlanBindingServiceImplTest {

    @Mock private TenantPlanBindingMapper bindingMapper;
    @Mock private BidSubscriptionMapper subscriptionMapper;
    @Mock private TenantMapper tenantMapper;
    @Mock private JwtUtils jwtUtils;

    private TenantPlanBindingServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TenantPlanBindingServiceImpl(
                bindingMapper, subscriptionMapper, tenantMapper, jwtUtils, new ObjectMapper());
        TenantContext.setTenantId(7L);
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    private BidSubscription plan(Long id, String code, String type, String flags) {
        BidSubscription sub = new BidSubscription();
        sub.setId(id);
        sub.setPlanCode(code);
        sub.setPlanName(code);
        sub.setPlanType(type);
        sub.setPriceCents(0L);
        sub.setMaxProjects(5);
        sub.setMaxSeats(5);
        sub.setCharQuota(100000L);
        sub.setModuleFlags(flags);
        sub.setStatus(BidSubscription.STATUS_ACTIVE);
        return sub;
    }

    private Tenant tenant(String planTier) {
        Tenant t = new Tenant();
        t.setId(7L);
        t.setPlanTier(planTier);
        return t;
    }

    /** bind() 内部调用静态 JwtUtils.getCurrentUserId()，用 mockStatic 打桩 */
    private PlanBindingDTO bindWithCreator(Long subscriptionId) {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(3L);
            return service.bind(subscriptionId);
        }
    }

    @Test
    void bindCreatesBindingAndAlignsTenantTier() {
        when(subscriptionMapper.selectById(10L)).thenReturn(plan(10L, "pro", "tier",
                "{\"draft\":true,\"check\":true,\"docx\":false,\"openapi\":true}"));
        when(bindingMapper.selectOne(any())).thenReturn(null);
        when(bindingMapper.insert(any(TenantPlanBinding.class))).thenAnswer(inv -> {
            inv.getArgument(0, TenantPlanBinding.class).setId(99L);
            return 1;
        });
        when(tenantMapper.selectById(7L)).thenReturn(tenant("free"));

        PlanBindingDTO dto = bindWithCreator(10L);

        assertEquals("pro", dto.getPlanCode());
        assertEquals("tier", dto.getPlanType());
        // tier 套餐对齐 tenant.plan_tier
        var captor = org.mockito.ArgumentCaptor.forClass(Tenant.class);
        verify(tenantMapper).updateById(captor.capture());
        assertEquals("pro", captor.getValue().getPlanTier());
    }

    @Test
    void bindIsIdempotentReactivatesExisting() {
        when(subscriptionMapper.selectById(10L)).thenReturn(plan(10L, "pro", "tier",
                "{\"draft\":true,\"check\":true}"));
        TenantPlanBinding existing = new TenantPlanBinding();
        existing.setId(5L);
        existing.setTenantId(7L);
        existing.setSubscriptionId(10L);
        existing.setStatus(TenantPlanBinding.STATUS_CANCELED);
        when(bindingMapper.selectOne(any())).thenReturn(existing);

        bindWithCreator(10L);

        verify(bindingMapper, never()).insert(any(TenantPlanBinding.class));
        verify(bindingMapper).updateById(existing);
        assertEquals(TenantPlanBinding.STATUS_ACTIVE, existing.getStatus());
        assertEquals(null, existing.getEndAt());
    }

    @Test
    void bindRejectsArchivedPlan() {
        BidSubscription archived = plan(10L, "pro", "tier", "{}");
        archived.setStatus(BidSubscription.STATUS_ARCHIVED);
        when(subscriptionMapper.selectById(10L)).thenReturn(archived);

        assertThrows(BusinessException.class, () -> service.bind(10L));
        verify(bindingMapper, never()).insert(any());
    }

    @Test
    void industryBindingDoesNotAlignTenantTier() {
        when(subscriptionMapper.selectById(20L)).thenReturn(plan(20L, "industry_construction", "industry",
                "{\"draft\":true,\"docx\":true}"));
        when(bindingMapper.selectOne(any())).thenReturn(null);

        bindWithCreator(20L);

        verify(tenantMapper, never()).updateById(any(Tenant.class));
    }

    @Test
    void unbindMarksCanceled() {
        TenantPlanBinding binding = new TenantPlanBinding();
        binding.setId(5L);
        binding.setTenantId(7L);
        binding.setSubscriptionId(10L);
        when(bindingMapper.selectOne(any())).thenReturn(binding);

        service.unbind(10L);

        assertEquals(TenantPlanBinding.STATUS_CANCELED, binding.getStatus());
        verify(bindingMapper).updateById(binding);
    }

    @Test
    void unbindUnknownThrows() {
        when(bindingMapper.selectOne(any())).thenReturn(null);
        assertThrows(BusinessException.class, () -> service.unbind(10L));
    }

    @Test
    void resolveCurrentTierPrefersActiveTierBinding() {
        TenantPlanBinding tierBinding = new TenantPlanBinding();
        tierBinding.setTenantId(7L);
        tierBinding.setSubscriptionId(10L);
        tierBinding.setStatus(TenantPlanBinding.STATUS_ACTIVE);
        when(bindingMapper.selectList(any())).thenReturn(List.of(tierBinding));
        when(subscriptionMapper.selectBatchIds(List.of(10L)))
                .thenReturn(List.of(plan(10L, "enterprise", "tier", "{}")));

        assertEquals("enterprise", service.resolveCurrentTier(7L));
    }

    @Test
    void resolveCurrentTierFallsBackToTenantTier() {
        when(bindingMapper.selectList(any())).thenReturn(List.of());
        when(tenantMapper.selectById(7L)).thenReturn(tenant("pro"));

        assertEquals("pro", service.resolveCurrentTier(7L));
    }

    @Test
    void grantedModulesUnionsFlagsAcrossBindings() {
        TenantPlanBinding a = new TenantPlanBinding();
        a.setTenantId(7L);
        a.setSubscriptionId(10L);
        a.setStatus(TenantPlanBinding.STATUS_ACTIVE);
        TenantPlanBinding b = new TenantPlanBinding();
        b.setTenantId(7L);
        b.setSubscriptionId(20L);
        b.setStatus(TenantPlanBinding.STATUS_ACTIVE);
        when(bindingMapper.selectList(any())).thenReturn(List.of(a, b));
        when(subscriptionMapper.selectBatchIds(List.of(10L, 20L))).thenReturn(List.of(
                plan(10L, "pro", "tier", "{\"draft\":true,\"check\":true,\"openapi\":true}"),
                plan(20L, "industry_construction", "industry", "{\"docx\":true}")));

        Set<String> modules = service.grantedModules(7L);

        assertEquals(Set.of("draft", "check", "openapi", "docx"), modules);
        assertTrue(service.hasModule(7L, "docx"));
        assertTrue(service.hasIndustry(7L, "industry_construction"));
    }
}
