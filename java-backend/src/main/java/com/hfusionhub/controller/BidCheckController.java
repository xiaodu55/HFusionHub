package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.BidCheckReport;
import com.hfusionhub.service.BidCheckService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 废标风险自检控制器（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/bid/check")
@RequiredArgsConstructor
@Tag(name = "废标自检", description = "废标风险自检与报告处理")
public class BidCheckController {

    private final BidCheckService bidCheckService;

    @PostMapping("/{id}")
    @Operation(summary = "执行废标自检", description = "对当前标书草稿自检并落库，推进项目至 checking")
    public R<Map<String, Object>> check(@PathVariable Long id) {
        return R.ok("自检完成", bidCheckService.check(id));
    }

    @GetMapping("/{id}/reports")
    @Operation(summary = "查询自检报告", description = "按严重度 critical→warning→info 排序")
    public R<List<BidCheckReport>> listReports(@PathVariable Long id) {
        return R.ok(bidCheckService.listReports(id));
    }

    @PutMapping("/report/{reportId}/status")
    @Operation(summary = "处理自检报告", description = "confirmed|fixed；critical 级必须人工确认后才能放行")
    public R<Void> updateReportStatus(@PathVariable Long reportId, @RequestParam String status) {
        bidCheckService.updateReportStatus(reportId, status);
        return R.ok();
    }
}
