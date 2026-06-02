package com.hfusionhub.service;

import com.hfusionhub.entity.BidTemplate;
import java.util.List;

/**
 * 标书模板服务（招投标垂直化 · P2-7 行业方案包 / 模板商城）
 *
 * <p>{@code bid_template.tenant_id} 可空 = 平台级模板（行业方案包基础）；
 * 非空 = 租户私有模板。本表已加入 {@code TENANT_IGNORE_TABLES}，租户查询须
 * 同时可见平台模板 + 自有模板，由服务层过滤。</p>
 *
 * @author HFusionHub Team
 */
public interface BidTemplateService {

    /** 租户可见模板（平台级 + 自有），可按行业过滤 */
    List<BidTemplate> listVisible(Long tenantId, String industry);

    /** 查询单个模板（仅平台级或本租户自有） */
    BidTemplate getByIdVisible(Long id, Long tenantId);

    /** 行业方案包预置模板（平台级 + 本租户） */
    List<BidTemplate> listByIndustry(String industry, Long tenantId);

    /** 新建租户私有模板 */
    BidTemplate create(BidTemplate template, Long tenantId, Long userId);

    /** 更新（仅本租户私有模板） */
    void update(BidTemplate template, Long tenantId);

    /** 归档（仅本租户私有模板） */
    void archive(Long id, Long tenantId);
}
