package com.hfusionhub.service;

import com.hfusionhub.entity.BidCheckReport;
import java.util.List;
import java.util.Map;

/**
 * 废标风险自检服务（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
public interface BidCheckService {

    /**
     * 对项目当前标书草稿执行废标自检并落库（先清空旧报告），推进项目至 checking。
     *
     * @param projectId 投标项目 ID
     * @return 本次自检统计 {total, critical, warning, info}
     */
    Map<String, Object> check(Long projectId);

    /**
     * 开放 API 路径的废标自检（P2-7 /openapi/bid/check）。
     *
     * <p>调用方须已置于 app 所属租户上下文（{@code TenantContext.runAs(tenantId)}），
     * 租户行拦截器据此过滤项目归属；此处按 tenantId 校验 openapi 模块开关。</p>
     *
     * @param projectId 投标项目 ID
     * @param tenantId  app 所属租户
     * @return 本次自检统计 {total, critical, warning, info}
     */
    Map<String, Object> checkForApi(Long projectId, Long tenantId);

    /**
     * 查询项目的自检报告（按严重度 critical→warning→info 排序）。
     */
    List<BidCheckReport> listReports(Long projectId);

    /**
     * 自检报告处理（P1-8）：open|confirmed|fixed。
     * critical 级 finding 必须人工 confirmed 才能放行。
     *
     * @param reportId 报告 ID
     * @param status   confirmed|fixed
     */
    void updateReportStatus(Long reportId, String status);
}
