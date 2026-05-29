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
