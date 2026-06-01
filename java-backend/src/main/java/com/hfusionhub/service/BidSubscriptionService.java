package com.hfusionhub.service;

import com.hfusionhub.entity.BidSubscription;
import java.util.List;

/**
 * 订阅套餐目录服务（招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
public interface BidSubscriptionService {

    /**
     * 平台内置套餐目录（tenant_id IS NULL 且 active），供租户选购。
     */
    List<BidSubscription> listPlatformPlans();

    /**
     * 平台管理员：全量套餐（含归档与租户自定义）。
     */
    List<BidSubscription> listAll();

    /**
     * 按套餐代码查询。
     */
    BidSubscription getByCode(String planCode);

    /**
     * 平台管理员：新建套餐。
     */
    BidSubscription create(BidSubscription subscription);

    /**
     * 平台管理员：更新套餐。
     */
    void update(BidSubscription subscription);

    /**
     * 平台管理员：归档套餐（不再可选）。
     */
    void archive(Long id);
}
