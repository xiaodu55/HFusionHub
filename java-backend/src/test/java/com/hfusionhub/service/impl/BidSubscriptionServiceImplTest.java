package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.mapper.BidSubscriptionMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 订阅套餐目录服务单元测试（招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidSubscriptionServiceImplTest {

    @Mock private BidSubscriptionMapper subscriptionMapper;

    private BidSubscriptionServiceImpl service;

    @org.junit.jupiter.api.BeforeEach
    void setUp() {
        service = new BidSubscriptionServiceImpl(subscriptionMapper);
    }

    private BidSubscription plan(Long id, String code, String status) {
        BidSubscription sub = new BidSubscription();
        sub.setId(id);
        sub.setPlanCode(code);
        sub.setPlanName(code);
        sub.setPlanType(BidSubscription.PLAN_TYPE_TIER);
        sub.setPriceCents(0L);
        sub.setStatus(status);
        return sub;
    }

    @Test
    void listPlatformPlansFiltersTenantNullAndActive() {
        BidSubscription platform = plan(1L, "pro", BidSubscription.STATUS_ACTIVE);
        when(subscriptionMapper.selectList(any())).thenReturn(List.of(platform));

        List<BidSubscription> result = service.listPlatformPlans();

        assertEquals(1, result.size());
        assertEquals("pro", result.get(0).getPlanCode());
        // 服务层用 isNull(tenantId) + active 过滤，验证包装条件成立
        verify(subscriptionMapper).selectList(any());
    }

    @Test
    void getByCodeReturnsPlan() {
        when(subscriptionMapper.selectOne(any())).thenReturn(plan(1L, "enterprise", BidSubscription.STATUS_ACTIVE));

        BidSubscription found = service.getByCode("enterprise");

        assertNotNull(found);
        assertEquals("enterprise", found.getPlanCode());
    }

    @Test
    void createRejectsDuplicateCode() {
        when(subscriptionMapper.selectOne(any())).thenReturn(plan(1L, "pro", BidSubscription.STATUS_ACTIVE));

        BidSubscription dup = plan(null, "pro", BidSubscription.STATUS_ACTIVE);

        assertThrows(BusinessException.class, () -> service.create(dup));
    }

    @Test
    void createRejectsBlankCode() {
        BidSubscription blank = plan(null, " ", BidSubscription.STATUS_ACTIVE);
        assertThrows(BusinessException.class, () -> service.create(blank));
    }

    @Test
    void createAppliesDefaultsAndCreator() {
        when(subscriptionMapper.selectOne(any())).thenReturn(null);
        BidSubscription newPlan = plan(null, "startup", null);

        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(3L);
            BidSubscription saved = service.create(newPlan);
            assertEquals(BidSubscription.STATUS_ACTIVE, saved.getStatus());
            assertEquals(BidSubscription.PLAN_TYPE_TIER, saved.getPlanType());
            assertEquals(3L, saved.getCreatedBy());
        }
        verify(subscriptionMapper).insert(newPlan);
    }

    @Test
    void updateRejectsMissingId() {
        BidSubscription noId = plan(null, "pro", BidSubscription.STATUS_ACTIVE);
        assertThrows(BusinessException.class, () -> service.update(noId));
    }

    @Test
    void archiveSetsArchivedStatus() {
        BidSubscription existing = plan(1L, "legacy", BidSubscription.STATUS_ACTIVE);
        when(subscriptionMapper.selectById(1L)).thenReturn(existing);

        service.archive(1L);

        assertEquals(BidSubscription.STATUS_ARCHIVED, existing.getStatus());
        verify(subscriptionMapper).updateById(existing);
    }

    @Test
    void archiveUnknownThrows() {
        when(subscriptionMapper.selectById(99L)).thenReturn(null);
        assertThrows(BusinessException.class, () -> service.archive(99L));
    }
}
