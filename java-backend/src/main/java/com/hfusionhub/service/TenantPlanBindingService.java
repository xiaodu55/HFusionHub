package com.hfusionhub.service;

import com.hfusionhub.dto.PlanBindingDTO;
import java.util.List;
import java.util.Set;

/**
 * 租户套餐绑定服务（招投标垂直化 · P2）
 *
 * <p>租户可绑定基础档位（tier）+ 多个行业方案包（industry）。绑定 tier 套餐时同步
 * {@code tenant.plan_tier}，与 {@code QuotaProperties.defaultLimit} 对齐（驱动既有的
 * 每日限额引擎，无需改动 {@code UsageLedgerServiceImpl}）。</p>
 *
 * @author HFusionHub Team
 */
public interface TenantPlanBindingService {

    /**
     * 当前租户（TenantContext）绑定套餐，返回绑定（幂等：已绑定则重新激活）。
     */
    PlanBindingDTO bind(Long subscriptionId);

    /**
     * 当前租户解绑套餐（置为 canceled）。
     */
    void unbind(Long subscriptionId);

    /**
     * 查询租户有效绑定（含套餐信息），status=active。
     */
    List<PlanBindingDTO> listActiveBindings(Long tenantId);

    /**
     * 解析租户当前基础档位：有效 tier 绑定 → tenant.plan_tier → "free"。
     */
    String resolveCurrentTier(Long tenantId);

    /**
     * 租户有效绑定并集授予的模块集合（draft/check/docx/openapi）。
     */
    Set<String> grantedModules(Long tenantId);

    /**
     * 租户是否拥有某模块（撰写/自检/docx/开放 API 开关）。
     */
    boolean hasModule(Long tenantId, String module);

    /**
     * 租户是否已绑定某行业方案包（按 plan_code，如 industry_construction）。
     */
    boolean hasIndustry(Long tenantId, String industryCode);
}
