package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.entity.AdsCostDaily;
import com.hfusionhub.entity.AdsEvalQuality;
import com.hfusionhub.entity.AdsModelShare;
import com.hfusionhub.entity.AdsToolSuccess;
import com.hfusionhub.entity.AnalyticsRealtimeMetric;
import com.hfusionhub.mapper.AdsCostDailyMapper;
import com.hfusionhub.mapper.AdsEvalQualityMapper;
import com.hfusionhub.mapper.AdsModelShareMapper;
import com.hfusionhub.mapper.AdsToolSuccessMapper;
import com.hfusionhub.mapper.AnalyticsRealtimeMetricMapper;
import com.hfusionhub.service.AnalyticsService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 运营分析服务实现 — 租户隔离在服务端强制,不信任前端传参。
 *
 * @author HFusionHub Team
 */
@Service
@RequiredArgsConstructor
public class AnalyticsServiceImpl implements AnalyticsService {

    /** 平台全局口径的租户哨兵值(与数仓 ADS 约定一致) */
    public static final long GLOBAL_TENANT = -1L;

    private final AdsCostDailyMapper adsCostDailyMapper;
    private final AdsModelShareMapper adsModelShareMapper;
    private final AdsToolSuccessMapper adsToolSuccessMapper;
    private final AdsEvalQualityMapper adsEvalQualityMapper;
    private final AnalyticsRealtimeMetricMapper realtimeMapper;

    /**
     * 解析租户过滤口径:
     * 平台管理员(crossTenant)可显式指定(null=不过滤,-1=平台全局,>0=指定租户);
     * 普通租户用户强制本租户,忽略任何前端传参。
     */
    private Long scope(Long paramTenantId) {
        if (TenantContext.isCrossTenant()) {
            return paramTenantId;
        }
        return TenantContext.requireTenantId();
    }

    @Override
    public Map<String, Object> overview(int days) {
        LocalDate to = LocalDate.now();
        LocalDate from = to.minusDays(Math.max(1, days) - 1L);
        Long scoped = scope(null);

        List<AdsCostDaily> rows;
        if (TenantContext.isCrossTenant()) {
            rows = adsCostDailyMapper.selectList(new LambdaQueryWrapper<AdsCostDaily>()
                    .between(AdsCostDaily::getStatDate, from, to));
        } else {
            Long own = TenantContext.requireTenantId();
            rows = adsCostDailyMapper.selectList(new LambdaQueryWrapper<AdsCostDaily>()
                    .eq(AdsCostDaily::getTenantId, own)
                    .between(AdsCostDaily::getStatDate, from, to));
        }
        long totalCalls = rows.stream().mapToLong(AdsCostDaily::getCallCount).sum();
        long totalTokens = rows.stream().mapToLong(AdsCostDaily::getTotalTokens).sum();
        double totalCost = rows.stream()
                .filter(r -> r.getTenantId() == null || r.getTenantId() > 0)   // 租户口径,避免全局行重复累计
                .mapToDouble(r -> r.getCostUsd() == null ? 0 : r.getCostUsd().doubleValue())
                .sum();

        Map<String, Object> realtime = latestRealtimeSnapshot(scoped);

        Map<String, Object> result = new HashMap<>();
        result.put("days", days);
        result.put("totalCalls", totalCalls);
        result.put("totalTokens", totalTokens);
        result.put("totalCostUsd", Math.round(totalCost * 1e4) / 1e4);
        result.put("realtime", realtime);
        return result;
    }

    private Map<String, Object> latestRealtimeSnapshot(Long scoped) {
        LocalDateTime since = LocalDateTime.now().minusMinutes(5);
        List<AnalyticsRealtimeMetric> rt = realtimeMapper.selectList(
                new LambdaQueryWrapper<AnalyticsRealtimeMetric>()
                        .gt(AnalyticsRealtimeMetric::getWindowStart, since));
        long requests = rt.stream().mapToLong(AnalyticsRealtimeMetric::getRequestCount).sum();
        double cost = rt.stream()
                .mapToDouble(m -> m.getTotalCost() == null ? 0 : m.getTotalCost().doubleValue())
                .sum();
        double avgLatency = rt.stream()
                .filter(m -> m.getRequestCount() != null && m.getRequestCount() > 0)
                .mapToLong(AnalyticsRealtimeMetric::getAvgLatencyMs).average().orElse(0);
        Map<String, Object> snapshot = new HashMap<>();
        snapshot.put("windowMinutes", 5);
        snapshot.put("requests", requests);
        snapshot.put("costUsd", Math.round(cost * 1e4) / 1e4);
        snapshot.put("avgLatencyMs", (long) avgLatency);
        return snapshot;
    }

    @Override
    public List<AdsCostDaily> costDaily(int days, Long tenantId) {
        LocalDate to = LocalDate.now();
        LocalDate from = to.minusDays(Math.max(1, days) - 1L);
        Long scoped = scope(tenantId);
        LambdaQueryWrapper<AdsCostDaily> wrapper = new LambdaQueryWrapper<>();
        if (scoped != null) {
            wrapper.eq(AdsCostDaily::getTenantId, scoped);
        }
        wrapper.between(AdsCostDaily::getStatDate, from, to)
                .orderByAsc(AdsCostDaily::getStatDate);
        return adsCostDailyMapper.selectList(wrapper);
    }

    @Override
    public List<AdsModelShare> modelShare(LocalDate date, Long tenantId) {
        LocalDate statDate = date != null ? date : LocalDate.now().minusDays(1);
        Long scoped = scope(tenantId);
        LambdaQueryWrapper<AdsModelShare> wrapper = new LambdaQueryWrapper<>();
        if (scoped != null) {
            wrapper.eq(AdsModelShare::getTenantId, scoped);
        }
        wrapper.eq(AdsModelShare::getStatDate, statDate)
                .orderByDesc(AdsModelShare::getCostUsd);
        return adsModelShareMapper.selectList(wrapper);
    }

    @Override
    public List<AdsToolSuccess> toolSuccess(int days, Long tenantId) {
        LocalDate from = LocalDate.now().minusDays(Math.max(1, days) - 1L);
        Long scoped = scope(tenantId);
        LambdaQueryWrapper<AdsToolSuccess> wrapper = new LambdaQueryWrapper<>();
        if (scoped != null) {
            wrapper.eq(AdsToolSuccess::getTenantId, scoped);
        }
        wrapper.ge(AdsToolSuccess::getStatDate, from)
                .orderByDesc(AdsToolSuccess::getStatDate)
                .orderByAsc(AdsToolSuccess::getStepType);
        return adsToolSuccessMapper.selectList(wrapper);
    }

    @Override
    public List<AdsEvalQuality> evalQuality(int days, Long tenantId) {
        LocalDate from = LocalDate.now().minusDays(Math.max(1, days) - 1L);
        Long scoped = scope(tenantId);
        LambdaQueryWrapper<AdsEvalQuality> wrapper = new LambdaQueryWrapper<>();
        if (scoped != null) {
            wrapper.eq(AdsEvalQuality::getTenantId, scoped);
        }
        wrapper.ge(AdsEvalQuality::getStatDate, from)
                .orderByAsc(AdsEvalQuality::getStatDate);
        return adsEvalQualityMapper.selectList(wrapper);
    }

    @Override
    public List<AnalyticsRealtimeMetric> realtime(int minutes, Long tenantId) {
        LocalDateTime since = LocalDateTime.now().minusMinutes(Math.max(1, minutes));
        Long scoped = scope(tenantId);
        LambdaQueryWrapper<AnalyticsRealtimeMetric> wrapper = new LambdaQueryWrapper<>();
        if (scoped != null) {
            wrapper.eq(AnalyticsRealtimeMetric::getTenantId, scoped);
        }
        wrapper.gt(AnalyticsRealtimeMetric::getWindowStart, since)
                .orderByDesc(AnalyticsRealtimeMetric::getWindowStart);
        return realtimeMapper.selectList(wrapper);
    }
}
