package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PlanBindingDTO;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantPlanBinding;
import com.hfusionhub.mapper.BidSubscriptionMapper;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantPlanBindingMapper;
import com.hfusionhub.service.TenantPlanBindingService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 租户套餐绑定服务实现（招投标垂直化 · P2）
 *
 * <p>绑定 tier 套餐时同步 {@code tenant.plan_tier}，与 {@code QuotaProperties.defaultLimit}
 * 对齐——既有的每日限额引擎（{@code UsageLedgerServiceImpl}）无需改动即可按新档位计费。
 * 行业方案包（industry）只授权模块/语料，不改档位。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantPlanBindingServiceImpl implements TenantPlanBindingService {

    private final TenantPlanBindingMapper bindingMapper;
    private final BidSubscriptionMapper subscriptionMapper;
    private final TenantMapper tenantMapper;
    private final JwtUtils jwtUtils;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional
    public PlanBindingDTO bind(Long subscriptionId) {
        BidSubscription subscription = subscriptionMapper.selectById(subscriptionId);
        if (subscription == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "套餐不存在");
        }
        if (!BidSubscription.STATUS_ACTIVE.equals(subscription.getStatus())) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "套餐已下架");
        }
        Long tenantId = TenantContext.requireTenantId();

        TenantPlanBinding binding = bindingMapper.selectOne(new LambdaQueryWrapper<TenantPlanBinding>()
                .eq(TenantPlanBinding::getTenantId, tenantId)
                .eq(TenantPlanBinding::getSubscriptionId, subscriptionId));
        if (binding != null) {
            binding.setStatus(TenantPlanBinding.STATUS_ACTIVE);
            binding.setEndAt(null);
            bindingMapper.updateById(binding);
            log.info("租户套餐绑定已重新激活: tenantId={}, subscriptionId={}", tenantId, subscriptionId);
        } else {
            binding = new TenantPlanBinding();
            binding.setTenantId(tenantId);
            binding.setSubscriptionId(subscriptionId);
            binding.setStartAt(LocalDateTime.now());
            binding.setStatus(TenantPlanBinding.STATUS_ACTIVE);
            binding.setCreatedBy(jwtUtils.getCurrentUserId());
            bindingMapper.insert(binding);
            log.info("租户套餐已绑定: tenantId={}, subscriptionId={}, planCode={}",
                    tenantId, subscriptionId, subscription.getPlanCode());
        }
        alignTenantTier(tenantId, subscription);
        return toDto(binding, subscription);
    }

    @Override
    @Transactional
    public void unbind(Long subscriptionId) {
        Long tenantId = TenantContext.requireTenantId();
        TenantPlanBinding binding = bindingMapper.selectOne(new LambdaQueryWrapper<TenantPlanBinding>()
                .eq(TenantPlanBinding::getTenantId, tenantId)
                .eq(TenantPlanBinding::getSubscriptionId, subscriptionId));
        if (binding == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "未绑定该套餐");
        }
        binding.setStatus(TenantPlanBinding.STATUS_CANCELED);
        bindingMapper.updateById(binding);
        log.info("租户套餐已解绑: tenantId={}, subscriptionId={}", tenantId, subscriptionId);
    }

    @Override
    public List<PlanBindingDTO> listActiveBindings(Long tenantId) {
        List<TenantPlanBinding> bindings = activeBindings(tenantId);
        List<PlanBindingDTO> result = new ArrayList<>();
        for (TenantPlanBinding binding : bindings) {
            BidSubscription subscription = subscriptionMapper.selectById(binding.getSubscriptionId());
            if (subscription != null) {
                result.add(toDto(binding, subscription));
            }
        }
        return result;
    }

    @Override
    public String resolveCurrentTier(Long tenantId) {
        for (TenantPlanBinding binding : activeBindings(tenantId)) {
            BidSubscription subscription = subscriptionMapper.selectById(binding.getSubscriptionId());
            if (subscription != null && BidSubscription.PLAN_TYPE_TIER.equals(subscription.getPlanType())) {
                return subscription.getPlanCode();
            }
        }
        Tenant tenant = tenantMapper.selectById(tenantId);
        return tenant != null && tenant.getPlanTier() != null ? tenant.getPlanTier() : "free";
    }

    @Override
    public Set<String> grantedModules(Long tenantId) {
        Set<String> modules = new HashSet<>();
        for (PlanBindingDTO dto : listActiveBindings(tenantId)) {
            modules.addAll(parseModuleFlags(dto.getModuleFlags()));
        }
        return modules;
    }

    @Override
    public boolean hasModule(Long tenantId, String module) {
        return grantedModules(tenantId).contains(module);
    }

    @Override
    public boolean hasIndustry(Long tenantId, String industryCode) {
        for (TenantPlanBinding binding : activeBindings(tenantId)) {
            BidSubscription subscription = subscriptionMapper.selectById(binding.getSubscriptionId());
            if (subscription != null && industryCode.equals(subscription.getPlanCode())) {
                return true;
            }
        }
        return false;
    }

    // ── 私有方法 ────────────────────────────────────────────────

    private List<TenantPlanBinding> activeBindings(Long tenantId) {
        return bindingMapper.selectList(new LambdaQueryWrapper<TenantPlanBinding>()
                .eq(TenantPlanBinding::getTenantId, tenantId)
                .eq(TenantPlanBinding::getStatus, TenantPlanBinding.STATUS_ACTIVE));
    }

    /** 对齐 tenant.plan_tier：仅 tier 档位套餐驱动 QuotaProperties 默认额度 */
    private void alignTenantTier(Long tenantId, BidSubscription subscription) {
        if (!BidSubscription.PLAN_TYPE_TIER.equals(subscription.getPlanType())) {
            return;
        }
        Tenant tenant = tenantMapper.selectById(tenantId);
        if (tenant != null && !subscription.getPlanCode().equals(tenant.getPlanTier())) {
            tenant.setPlanTier(subscription.getPlanCode());
            tenantMapper.updateById(tenant);
            log.info("租户套餐档位已对齐: tenantId={}, planTier={}", tenantId, subscription.getPlanCode());
        }
    }

    /** 解析 module_flags JSON 为已启用模块集合 */
    private Set<String> parseModuleFlags(String moduleFlags) {
        Set<String> enabled = new HashSet<>();
        if (moduleFlags == null || moduleFlags.isBlank()) {
            return enabled;
        }
        try {
            Map<String, Object> map = objectMapper.readValue(moduleFlags, Map.class);
            map.forEach((key, value) -> {
                if (Boolean.TRUE.equals(value) || "1".equals(String.valueOf(value))) {
                    enabled.add(String.valueOf(key));
                }
            });
        } catch (Exception e) {
            log.warn("解析套餐 module_flags 失败: {}", moduleFlags, e);
        }
        return enabled;
    }

    private PlanBindingDTO toDto(TenantPlanBinding binding, BidSubscription subscription) {
        PlanBindingDTO dto = new PlanBindingDTO();
        dto.setBindingId(binding.getId());
        dto.setSubscriptionId(subscription.getId());
        dto.setPlanCode(subscription.getPlanCode());
        dto.setPlanName(subscription.getPlanName());
        dto.setPlanType(subscription.getPlanType());
        dto.setPriceCents(subscription.getPriceCents());
        dto.setMaxProjects(subscription.getMaxProjects());
        dto.setMaxSeats(subscription.getMaxSeats());
        dto.setCharQuota(subscription.getCharQuota());
        dto.setModuleFlags(subscription.getModuleFlags());
        dto.setStatus(binding.getStatus());
        dto.setStartAt(binding.getStartAt());
        dto.setEndAt(binding.getEndAt());
        return dto;
    }
}
