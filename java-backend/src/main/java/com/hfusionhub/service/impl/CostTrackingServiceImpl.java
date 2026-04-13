package com.hfusionhub.service.impl;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.CostSummaryDTO;
import com.hfusionhub.dto.DailyCostDTO;
import com.hfusionhub.dto.ModelCostDTO;
import com.hfusionhub.dto.TenantCostSummaryDTO;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.ModelUsageRecordMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 模型调用成本追踪服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class CostTrackingServiceImpl implements CostTrackingService {

    /** 默认统计天数 */
    private static final int DEFAULT_DAYS = 30;
    /** 统计天数上限 */
    private static final int MAX_DAYS = 90;

    private final ModelUsageRecordMapper modelUsageRecordMapper;
    private final UserMapper userMapper;

    @Override
    @Transactional
    public void record(ModelUsageRecord record) {
        if (record.getUserId() == null) {
            throw new BusinessException("成本记录缺少用户ID");
        }
        if (!StringUtils.hasText(record.getModel()) || !StringUtils.hasText(record.getProvider())) {
            throw new BusinessException("成本记录缺少模型或提供商");
        }
        if (!StringUtils.hasText(record.getRequestType())) {
            throw new BusinessException("成本记录缺少请求类型");
        }
        // 缺省字段归一为 0，避免 NULL 入库（列带 NOT NULL DEFAULT 0）
        if (record.getPromptTokens() == null) record.setPromptTokens(0);
        if (record.getCompletionTokens() == null) record.setCompletionTokens(0);
        if (record.getTotalTokens() == null) {
            record.setTotalTokens(record.getPromptTokens() + record.getCompletionTokens());
        }
        if (record.getCostUsd() == null) record.setCostUsd(BigDecimal.ZERO);
        if (record.getLatencyMs() == null) record.setLatencyMs(0);

        modelUsageRecordMapper.insert(record);
        log.debug("成本记录已落账: userId={} model={} tokens={} cost={}",
                record.getUserId(), record.getModel(), record.getTotalTokens(), record.getCostUsd());
    }

    @Override
    public List<DailyCostDTO> getUserDailyCost(Long userId, int days) {
        int effectiveDays = Math.max(1, Math.min(days, MAX_DAYS));
        LocalDateTime startDate = LocalDate.now().minusDays(effectiveDays).atStartOfDay();
        return modelUsageRecordMapper.selectDailyCostByUser(userId, startDate);
    }

    @Override
    public TenantCostSummaryDTO getTenantCostSummary(Long tenantId, LocalDateTime start, LocalDateTime end) {
        LocalDateTime startDate = start != null ? start : LocalDate.now().minusDays(DEFAULT_DAYS).atStartOfDay();
        LocalDateTime endDate = end != null ? end : LocalDateTime.now();

        // 以目标租户上下文执行，保证租户行拦截器附加的 tenant_id 过滤与查询参数一致
        // （支持平台管理员经 X-Target-Tenant 头跨租户查看）。
        Map<String, Object> total = TenantContext.runAs(tenantId, () ->
                modelUsageRecordMapper.selectTotalCostByTenant(tenantId, startDate, endDate));
        List<Map<String, Object>> rows = TenantContext.runAs(tenantId, () ->
                modelUsageRecordMapper.selectCostBreakdown(tenantId, null, startDate, endDate));

        TenantCostSummaryDTO dto = new TenantCostSummaryDTO();
        dto.setTenantId(tenantId);
        dto.setStartDate(startDate);
        dto.setEndDate(endDate);
        if (total != null) {
            dto.setTotalCost(toBigDecimal(getMapValue(total, "total_cost")));
            dto.setTotalTokens(toLong(getMapValue(total, "total_tokens")));
            dto.setTotalRequests(toLong(getMapValue(total, "total_requests")));
        } else {
            dto.setTotalCost(BigDecimal.ZERO);
            dto.setTotalTokens(0L);
            dto.setTotalRequests(0L);
        }
        dto.setModelBreakdown(toModelCostList(rows));
        return dto;
    }

    @Override
    public CostSummaryDTO getCostSummary(Long userId) {
        return getCostSummary(userId, DEFAULT_DAYS);
    }

    @Override
    public CostSummaryDTO getCostSummary(Long userId, int days) {
        User user = userMapper.selectById(userId);
        Long tenantId = user != null ? user.getTenantId() : null;

        int effectiveDays = Math.max(1, Math.min(days, MAX_DAYS));
        LocalDateTime startDate = LocalDate.now().minusDays(effectiveDays).atStartOfDay();
        LocalDateTime endDate = LocalDateTime.now();

        Map<String, Object> total = modelUsageRecordMapper.selectTotalCostByUser(userId, startDate, endDate);
        List<Map<String, Object>> rows = modelUsageRecordMapper.selectCostBreakdown(tenantId, userId, startDate, endDate);

        CostSummaryDTO dto = new CostSummaryDTO();
        dto.setUserId(userId);
        dto.setTenantId(tenantId);
        dto.setPeriodStart(startDate);
        dto.setPeriodEnd(endDate);
        if (total != null) {
            dto.setTotalCost(toBigDecimal(getMapValue(total, "total_cost")));
            dto.setTotalTokens(toLong(getMapValue(total, "total_tokens")));
            dto.setTotalRequests(toLong(getMapValue(total, "total_requests")));
        } else {
            dto.setTotalCost(BigDecimal.ZERO);
            dto.setTotalTokens(0L);
            dto.setTotalRequests(0L);
        }
        dto.setModelBreakdown(toModelCostList(rows));
        dto.setCurrentMonthCost(BigDecimal.valueOf(currentMonthCost(userId)));
        dto.setEstimatedMonthCost(BigDecimal.valueOf(getCurrentMonthEstimate(userId)));
        return dto;
    }

    @Override
    public List<ModelCostDTO> getUserModelCost(Long userId, int days) {
        User user = userMapper.selectById(userId);
        Long tenantId = user != null ? user.getTenantId() : null;
        int effectiveDays = Math.max(1, Math.min(days, MAX_DAYS));
        LocalDateTime startDate = LocalDate.now().minusDays(effectiveDays).atStartOfDay();
        return toModelCostList(modelUsageRecordMapper.selectCostBreakdown(
                tenantId, userId, startDate, LocalDateTime.now()));
    }

    @Override
    public double getCurrentMonthEstimate(Long userId) {
        YearMonth month = YearMonth.now();
        LocalDateTime monthStart = month.atDay(1).atStartOfDay();
        LocalDateTime now = LocalDateTime.now();
        double costSoFar = currentMonthCost(userId);
        if (costSoFar <= 0) {
            return 0;
        }
        int daysInMonth = month.lengthOfMonth();
        int daysElapsed = now.getDayOfMonth();
        if (daysElapsed <= 0) {
            return costSoFar;
        }
        return BigDecimal.valueOf(costSoFar)
                .multiply(BigDecimal.valueOf(daysInMonth))
                .divide(BigDecimal.valueOf(daysElapsed), 6, RoundingMode.HALF_UP)
                .doubleValue();
    }

    // ================================================================
    // 内部辅助
    // ================================================================

    /** 本月已发生成本（美元） */
    private double currentMonthCost(Long userId) {
        YearMonth month = YearMonth.now();
        Map<String, Object> total = modelUsageRecordMapper.selectTotalCostByUser(
                userId, month.atDay(1).atStartOfDay(), LocalDateTime.now());
        Object cost = total == null ? null : getMapValue(total, "total_cost");
        if (cost == null) {
            return 0;
        }
        return ((Number) cost).doubleValue();
    }

    private List<ModelCostDTO> toModelCostList(List<Map<String, Object>> rows) {
        List<ModelCostDTO> list = new ArrayList<>(rows.size());
        for (Map<String, Object> row : rows) {
            ModelCostDTO dto = new ModelCostDTO();
            Object model = getMapValue(row, "model");
            dto.setModel(model != null ? model.toString() : "unknown");
            dto.setRequestCount(toLong(getMapValue(row, "request_count")));
            dto.setTotalTokens(toLong(getMapValue(row, "total_tokens")));
            dto.setTotalCost(toBigDecimal(getMapValue(row, "total_cost")));
            list.add(dto);
        }
        return list;
    }

    /**
     * 大小写不敏感地读取查询结果 Map。
     * MySQL 保留别名大小写，H2 将未加引号的别名转为大写，两种方言统一处理。
     */
    private static Object getMapValue(Map<String, Object> map, String key) {
        if (map == null || key == null) {
            return null;
        }
        Object value = map.get(key);
        if (value != null) {
            return value;
        }
        value = map.get(key.toUpperCase());
        if (value != null) {
            return value;
        }
        return map.get(key.toLowerCase());
    }

    private static Long toLong(Object value) {
        return value == null ? 0L : ((Number) value).longValue();
    }

    private static BigDecimal toBigDecimal(Object value) {
        return value == null ? BigDecimal.ZERO : new BigDecimal(value.toString());
    }
}
