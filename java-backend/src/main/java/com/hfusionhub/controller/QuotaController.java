package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckLogin;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.QuotaSummaryDTO;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 租户配额控制器 - 展示当前租户今日用量与日限额
 *
 * <p>读 {@link UsageLedgerService}（当前线程租户上下文），只读不预占。</p>
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/quota")
@RequiredArgsConstructor
@SaCheckLogin
@Tag(name = "租户配额", description = "当前租户今日用量与日限额查询")
public class QuotaController {

    private final UsageLedgerService usageLedgerService;

    @Operation(summary = "配额摘要", description = "各计量项今日已用/预占/日限额/剩余（当前租户）")
    @GetMapping("/summary")
    public R<List<QuotaSummaryDTO>> summary() {
        List<QuotaSummaryDTO> result = new ArrayList<>();
        for (UsageMeter meter : UsageMeter.values()) {
            long committed = usageLedgerService.currentCommitted(meter);
            long reserved = usageLedgerService.currentReserved(meter);
            long limit = usageLedgerService.effectiveDailyLimit(meter);
            long used = committed + reserved;
            result.add(QuotaSummaryDTO.builder()
                    .meter(meter.getCode())
                    .label(labelOf(meter))
                    .unit(unitOf(meter))
                    .committed(committed)
                    .reserved(reserved)
                    .used(used)
                    .dailyLimit(limit)
                    .remaining(Math.max(limit - used, 0))
                    .percent(limit > 0 ? Math.min(used * 100.0 / limit, 999.0) : 0)
                    .build());
        }
        return R.ok(result);
    }

    private String labelOf(UsageMeter meter) {
        return switch (meter) {
            case CHAT_TOKENS -> "对话 Token";
            case AGENT_TOKENS -> "Agent Token";
            case INDEX_CHUNKS -> "文档索引分块";
            case PLUGIN_EXECUTIONS -> "插件执行";
        };
    }

    private String unitOf(UsageMeter meter) {
        return meter == UsageMeter.PLUGIN_EXECUTIONS ? "次" : "Token";
    }
}
