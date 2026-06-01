package com.hfusionhub.service;

import java.util.Map;

/**
 * 投标套餐模块开关（招投标垂直化 · P2-2）
 *
 * <p>模块是否可用 = 套餐授权（{@code tenant_plan_binding.module_flags}）AND
 * 平台 FeatureFlag 运营开关（{@code bid.module.{module}}，默认全局开）。
 * 前者是商业资格底线，后者提供全局下架 / 环境灰度 / 租户覆盖。</p>
 *
 * @author HFusionHub Team
 */
public interface BidPlanGateService {

    /** 租户某模块是否可用（套餐授权 且 平台开关未关闭） */
    boolean isModuleEnabled(Long tenantId, String module);

    /**
     * 校验模块开通，未开通抛 {@link com.hfusionhub.common.exception.BusinessException}(403)
     *
     * @param actionLabel 操作名（用于错误提示，如"标书撰写"）
     */
    void requireModule(Long tenantId, String module, String actionLabel);

    /** 全部模块开关状态（供前端按模块禁用入口） */
    Map<String, Boolean> moduleStatus(Long tenantId);
}
