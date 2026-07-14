package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.InternalTokenGuard;
import com.hfusionhub.service.impl.AnalyticsBatchRunner;
import io.swagger.v3.oas.annotations.Hidden;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 内部大数据回补端点 — 运维/调度触发指定 dt 的批处理管线。
 *
 * <p>受 X-Internal-Token(常量时间比较)保护。用途:数据回补(kill 作业后
 * 重跑)、数据制造器灌数后的首次入仓、门禁失败修复后的重放。同步执行
 * (Spark 作业分钟级),失败返回管线日志 id 供 bigdata_batch_run_log 排查。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Hidden
@RestController
@RequestMapping("/internal/analytics")
@RequiredArgsConstructor
@Tag(name = "Internal Analytics", description = "Token-protected analytics batch backfill")
public class InternalAnalyticsController {

    private final AnalyticsBatchRunner batchRunner;

    @Value("${python-ai.internal-token:}")
    private String expectedToken;

    @PostMapping("/batch/run")
    public R<Map<String, Object>> runBatch(@RequestBody Map<String, Object> body,
                                           HttpServletRequest request) {
        if (!InternalTokenGuard.isAuthorized(expectedToken, request.getHeader("X-Internal-Token"))) {
            return R.fail(403, "Forbidden: invalid or missing X-Internal-Token");
        }
        Object rawDate = body.get("date");
        if (!(rawDate instanceof String dateStr) || dateStr.isBlank()) {
            return R.fail(400, "date (YYYY-MM-DD) is required");
        }
        LocalDate date;
        try {
            date = LocalDate.parse(dateStr);
        } catch (DateTimeParseException e) {
            return R.fail(400, "date must be YYYY-MM-DD");
        }

        log.info("[analytics-backfill] manual pipeline trigger dt={}", date);
        List<Long> stepLogIds = batchRunner.runPipeline(date, null);
        return R.ok(Map.of(
                "date", date.toString(),
                "stepLogIds", stepLogIds,
                "hint", "执行明细见 bigdata_batch_run_log(status/exit_code/log_excerpt)"));
    }
}
