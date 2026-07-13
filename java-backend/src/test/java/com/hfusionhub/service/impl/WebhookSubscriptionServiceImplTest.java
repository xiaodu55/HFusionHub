package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.User;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.mapper.WebhookDeliveryMapper;
import com.hfusionhub.mapper.WebhookSubscriptionMapper;
import com.hfusionhub.webhook.WebhookDispatcher;
import com.hfusionhub.webhook.WebhookEventTypes;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

/**
 * WebhookSubscriptionServiceImpl 单元测试 — 订阅管理、归属校验与投递历史。
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class WebhookSubscriptionServiceImplTest {

    private static final Long USER_ID = 1L;

    @Mock
    private WebhookSubscriptionMapper subscriptionMapper;

    @Mock
    private WebhookDeliveryMapper deliveryMapper;

    @Mock
    private UserMapper userMapper;

    @Mock
    private WebhookDispatcher webhookDispatcher;

    private WebhookSubscriptionServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new WebhookSubscriptionServiceImpl(
                subscriptionMapper, deliveryMapper, userMapper, webhookDispatcher);
    }

    private WebhookSubscription validSubscription() {
        WebhookSubscription sub = new WebhookSubscription();
        sub.setName("完成通知");
        sub.setUrl("https://ops.example.com/hook");
        sub.setEvents(List.of(WebhookEventTypes.AGENT_TASK_COMPLETED));
        return sub;
    }

    @Test
    void createRejectsBlankName() {
        WebhookSubscription sub = validSubscription();
        sub.setName(" ");

        assertThatThrownBy(() -> service.create(USER_ID, sub))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("名称不能为空");
    }

    @Test
    void createRejectsNonHttpUrl() {
        WebhookSubscription sub = validSubscription();
        sub.setUrl("ftp://ops.example.com/hook");

        assertThatThrownBy(() -> service.create(USER_ID, sub))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("http");
    }

    @Test
    void createRejectsUnknownEventType() {
        WebhookSubscription sub = validSubscription();
        sub.setEvents(List.of("unknown.event"));

        assertThatThrownBy(() -> service.create(USER_ID, sub))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不支持的事件类型");
    }

    @Test
    void createRejectsMissingUser() {
        when(userMapper.selectById(USER_ID)).thenReturn(null);

        assertThatThrownBy(() -> service.create(USER_ID, validSubscription()))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("用户不存在");
    }

    @Test
    void createFillsSecretAndTenant() {
        User user = new User();
        user.setTenantId(7L);
        when(userMapper.selectById(USER_ID)).thenReturn(user);

        WebhookSubscription saved = service.create(USER_ID, validSubscription());

        assertThat(saved.getTenantId()).isEqualTo(7L);
        assertThat(saved.getSecret()).isNotBlank().hasSize(32);
        assertThat(saved.getIsActive()).isEqualTo(1);
        verify(subscriptionMapper).insert(saved);
    }

    @Test
    void createKeepsProvidedSecret() {
        User user = new User();
        user.setTenantId(7L);
        when(userMapper.selectById(USER_ID)).thenReturn(user);
        WebhookSubscription sub = validSubscription();
        sub.setSecret("my-secret");

        WebhookSubscription saved = service.create(USER_ID, sub);

        assertThat(saved.getSecret()).isEqualTo("my-secret");
    }

    @Test
    void getRejectsOtherUsersSubscription() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(2L);
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);

        assertThatThrownBy(() -> service.get(USER_ID, 5L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权");
    }

    @Test
    void setActiveTogglesFlag() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(USER_ID);
        existing.setIsActive(1);
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);

        WebhookSubscription updated = service.setActive(USER_ID, 5L, false);

        assertThat(updated.getIsActive()).isEqualTo(0);
        verify(subscriptionMapper).updateById(existing);
    }

    @Test
    void updateValidatesNewUrl() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(USER_ID);
        existing.setUrl("https://old.example.com/hook");
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);
        WebhookSubscription patch = new WebhookSubscription();
        patch.setUrl("javascript:alert(1)");

        assertThatThrownBy(() -> service.update(USER_ID, 5L, patch))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("http");
    }

    @Test
    void deleteRemovesOwnedSubscription() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(USER_ID);
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);

        service.delete(USER_ID, 5L);

        verify(subscriptionMapper).deleteById(5L);
    }

    @Test
    void deliveryHistoryClampsPageSizeAndReturnsEnvelope() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(USER_ID);
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);
        WebhookDelivery delivery = new WebhookDelivery();
        delivery.setSubscriptionId(5L);
        delivery.setCreatedAt(LocalDateTime.now());
        when(deliveryMapper.selectList(any())).thenReturn(List.of(delivery));
        when(deliveryMapper.selectCount(any())).thenReturn(11L);

        PageResult<WebhookDelivery> result = service.deliveryHistory(USER_ID, 5L, 1, 999);

        assertThat(result.getTotal()).isEqualTo(11L);
        assertThat(result.getRecords()).hasSize(1);
    }

    @Test
    void deliveryHistoryRejectsForeignSubscription() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(2L);
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);

        assertThatThrownBy(() -> service.deliveryHistory(USER_ID, 5L, 1, 20))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权");
    }

    @Test
    void testFireDelegatesToDispatcher() {
        WebhookSubscription existing = new WebhookSubscription();
        existing.setId(5L);
        existing.setUserId(USER_ID);
        existing.setName("完成通知");
        when(subscriptionMapper.selectById(5L)).thenReturn(existing);
        WebhookDelivery delivery = new WebhookDelivery();
        when(webhookDispatcher.deliverSync(any(), anyString(), any())).thenReturn(delivery);

        WebhookDelivery result = service.testFire(USER_ID, 5L);

        assertThat(result).isSameAs(delivery);
        verify(webhookDispatcher).deliverSync(
                org.mockito.ArgumentMatchers.same(existing), org.mockito.ArgumentMatchers.eq("test"), any());
    }
}
