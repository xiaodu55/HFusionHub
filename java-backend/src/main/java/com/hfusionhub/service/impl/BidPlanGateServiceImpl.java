package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.PlanBindingDTO;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.FeatureFlagService;
import com.hfusionhub.service.TenantPlanBindingService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 投标套餐模块开关实现（招投标垂直化 · P2-2）
 *
 * <p>评估规则：{@code 套餐授权(module) && featureFlag.isEnabled(bid.module.{module}, tenant)}。
 * 套餐授权来自 {@link TenantPlanBindingServiceImpl#hasModule}（P2-1 落库）；FeatureFlag 为
 * 平台运营开关（V71 预置 4 个，全局默认开，可租户/环境覆盖）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidPlanGateServiceImpl implements BidPlanGateService {

    private static final String MODULE_FLAG_PREFIX = "bid.module.";

    private final TenantPlanBindingService bindingService;
    private final FeatureFlagService featureFlagService;
    private final TenantMemberMapper tenantMemberMapper;

    /** 功能开关求值环境（默认 prod），V71 预置开关为全局开 */
    @Value("${hfusionhub.env:prod}")
    private String environment;

    @Override
    public boolean isModuleEnabled(Long tenantId, String module) {
        if (module == null || !BidSubscription.MODULE_KEYS.contains(module)) {
            return false;
        }
        if (!bindingService.hasModule(tenantId, module)) {
            return false;
        }
        return featureFlagService.isEnabled(MODULE_FLAG_PREFIX + module, null, null, tenantId, environment);
    }

    @Override
    public void requireModule(Long tenantId, String module, String actionLabel) {
        if (!isModuleEnabled(tenantId, module)) {
            log.warn("投标套餐模块未开通被拦截: tenantId={}, module={}, action={}",
                    tenantId, module, actionLabel);
            throw new BusinessException(StatusCode.FORBIDDEN,
                    actionLabel + "需要开通「" + moduleLabel(module) + "」模块，请在套餐中心升级后重试");
        }
    }

    @Override
    public Map<String, Boolean> moduleStatus(Long tenantId) {
        Map<String, Boolean> status = new HashMap<>();
        for (String module : BidSubscription.MODULE_KEYS) {
            status.put(module, isModuleEnabled(tenantId, module));
        }
        return status;
    }

    @Override
    public void requireSeatAvailable(Long tenantId) {
        List<PlanBindingDTO> bindings = bindingService.listActiveBindings(tenantId);
        Integer maxSeats = null;
        for (PlanBindingDTO binding : bindings) {
            if (BidSubscription.PLAN_TYPE_TIER.equals(binding.getPlanType())
                    && binding.getMaxSeats() != null
                    && (maxSeats == null || binding.getMaxSeats() > maxSeats)) {
                maxSeats = binding.getMaxSeats();
            }
        }
        if (maxSeats == null) {
            return; // 未绑定 tier 套餐或无坐席上限，放行
        }
        Long seatsUsed = tenantMemberMapper.selectCount(new LambdaQueryWrapper<TenantMember>()
                .eq(TenantMember::getTenantId, tenantId));
        if (seatsUsed != null && seatsUsed >= maxSeats) {
            log.warn("套餐坐席已满被拦截: tenantId={}, seatsUsed={}, maxSeats={}",
                    tenantId, seatsUsed, maxSeats);
            throw new BusinessException(StatusCode.FORBIDDEN,
                    "当前套餐坐席已满（" + maxSeats + " 席），请升级套餐增加坐席");
        }
    }

    private String moduleLabel(String module) {
        return switch (module) {
            case BidSubscription.MODULE_DRAFT -> "标书撰写";
            case BidSubscription.MODULE_CHECK -> "废标自检";
            case BidSubscription.MODULE_DOCX -> "DOCX 导出";
            case BidSubscription.MODULE_OPENAPI -> "投标开放 API";
            default -> module;
        };
    }
}
