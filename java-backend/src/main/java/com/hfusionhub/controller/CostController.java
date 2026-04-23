package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.CostSummaryDTO;
import com.hfusionhub.dto.DailyCostDTO;
import com.hfusionhub.dto.ModelCostDTO;
import com.hfusionhub.dto.TenantCostSummaryDTO;
import com.hfusionhub.service.CostTrackingService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 模型调用成本追踪控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/cost")
@RequiredArgsConstructor
@Tag(name = "成本追踪", description = "模型调用成本统计与预测")
public class CostController {

    private final CostTrackingService costTrackingService;

    @GetMapping("/summary")
    @Operation(summary = "当前用户成本汇总（近30天 + 本月预估 + 按模型分组）")
    public R<CostSummaryDTO> summary(@RequestParam(defaultValue = "30") int days) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(costTrackingService.getCostSummary(userId, days));
    }

    @GetMapping("/tenant/{tenantId}")
    @Operation(summary = "租户级成本汇总（管理员）")
    @SaCheckRole("admin")
    public R<TenantCostSummaryDTO> tenantSummary(
            @PathVariable Long tenantId,
            @RequestParam(required = false) String start,
            @RequestParam(required = false) String end) {
        LocalDateTime startDate = parseDateParam(start);
        LocalDateTime endDate = parseDateParam(end);
        return R.ok(costTrackingService.getTenantCostSummary(tenantId, startDate, endDate));
    }

    @GetMapping("/daily")
    @Operation(summary = "当前用户每日成本明细（图表数据）")
    public R<List<DailyCostDTO>> daily(@RequestParam(defaultValue = "30") int days) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(costTrackingService.getUserDailyCost(userId, days));
    }

    @GetMapping("/models")
    @Operation(summary = "当前用户按模型汇总成本")
    public R<List<ModelCostDTO>> models(@RequestParam(defaultValue = "30") int days) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(costTrackingService.getUserModelCost(userId, days));
    }

    /**
     * 解析日期参数：支持 yyyy-MM-dd（当日零点）与 ISO 时间，非法时返回 null（走服务端默认）。
     */
    private LocalDateTime parseDateParam(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(value).atStartOfDay();
        } catch (DateTimeParseException ignored) {
            // fall through
        }
        try {
            return LocalDateTime.parse(value);
        } catch (DateTimeParseException e) {
            return null;
        }
    }
}
