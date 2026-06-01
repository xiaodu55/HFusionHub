package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.mapper.BidSubscriptionMapper;
import com.hfusionhub.service.BidSubscriptionService;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 订阅套餐目录服务实现（招投标垂直化 · P2）
 *
 * <p>本表为平台目录（已加入 {@code TENANT_IGNORE_TABLES}），租户查询可见全目录；
 * 非空 tenant_id 的租户自定义套餐由服务层自行过滤，不经租户行拦截器。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidSubscriptionServiceImpl implements BidSubscriptionService {

    private final BidSubscriptionMapper subscriptionMapper;

    @Override
    public List<BidSubscription> listPlatformPlans() {
        return subscriptionMapper.selectList(new LambdaQueryWrapper<BidSubscription>()
                .isNull(BidSubscription::getTenantId)
                .eq(BidSubscription::getStatus, BidSubscription.STATUS_ACTIVE)
                .orderByAsc(BidSubscription::getPlanType)
                .orderByAsc(BidSubscription::getPriceCents));
    }

    @Override
    public List<BidSubscription> listAll() {
        return subscriptionMapper.selectList(new LambdaQueryWrapper<BidSubscription>()
                .orderByAsc(BidSubscription::getPlanType)
                .orderByAsc(BidSubscription::getPriceCents));
    }

    @Override
    public BidSubscription getByCode(String planCode) {
        return subscriptionMapper.selectOne(new LambdaQueryWrapper<BidSubscription>()
                .eq(BidSubscription::getPlanCode, planCode));
    }

    @Override
    @Transactional
    public BidSubscription create(BidSubscription subscription) {
        if (subscription.getPlanCode() == null || subscription.getPlanCode().isBlank()) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "套餐代码不能为空");
        }
        if (getByCode(subscription.getPlanCode()) != null) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "套餐代码已存在: " + subscription.getPlanCode());
        }
        if (subscription.getStatus() == null) {
            subscription.setStatus(BidSubscription.STATUS_ACTIVE);
        }
        if (subscription.getPlanType() == null) {
            subscription.setPlanType(BidSubscription.PLAN_TYPE_TIER);
        }
        subscription.setCreatedBy(JwtUtils.getCurrentUserId());
        subscriptionMapper.insert(subscription);
        log.info("订阅套餐已创建: planCode={}, planName={}", subscription.getPlanCode(), subscription.getPlanName());
        return subscription;
    }

    @Override
    @Transactional
    public void update(BidSubscription subscription) {
        if (subscription.getId() == null) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "缺少套餐 ID");
        }
        subscriptionMapper.updateById(subscription);
        log.info("订阅套餐已更新: id={}", subscription.getId());
    }

    @Override
    @Transactional
    public void archive(Long id) {
        BidSubscription subscription = subscriptionMapper.selectById(id);
        if (subscription == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "套餐不存在");
        }
        subscription.setStatus(BidSubscription.STATUS_ARCHIVED);
        subscriptionMapper.updateById(subscription);
        log.info("订阅套餐已归档: id={}, planCode={}", id, subscription.getPlanCode());
    }
}
