package com.hfusionhub.service.impl;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.FeatureFlagService;
import com.hfusionhub.service.TenantPlanBindingService;
import java.util.HashMap;
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
