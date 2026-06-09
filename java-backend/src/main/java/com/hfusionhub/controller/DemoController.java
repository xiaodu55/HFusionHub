package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.service.BidDemoImportService;
import com.hfusionhub.service.DemoImportService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 演示数据控制器 — 一键导入各菜单示例数据，帮助新用户快速上手
 *
 * <p>所有端点受 {@code DEMO_ENDPOINTS_ENABLED} 门控（application.yml {@code app.demo.endpoints-enabled}，
 * 默认 true 便于开发/演示；生产部署通过 deploy/.env 默认关闭）。/clear 系列具有数据破坏性，
 * 生产环境保持关闭可避免误触发。
 *
 * @author HFusionHub Team
 */
@Tag(name = "演示数据", description = "各菜单示例数据一键导入")
@RestController
@RequestMapping("/demo")
@RequiredArgsConstructor
public class DemoController {

    private final DemoImportService demoImportService;
    private final BidDemoImportService bidDemoImportService;

    /** 演示数据端点总开关（生产默认关闭，见 deploy/.env.example） */
    @Value("${app.demo.endpoints-enabled:true}")
    private boolean demoEndpointsEnabled;

    private <T> R<T> checkEnabled() {
        if (!demoEndpointsEnabled) {
            return R.fail(403, "演示数据功能已关闭（DEMO_ENDPOINTS_ENABLED=false），如需使用请在环境配置中开启");
        }
        return null;
    }

    @Operation(summary = "导入演示数据", description = "一键导入各菜单示例数据：知识库文档、回答方案、我的笔记、我的记忆、应用发布、公告（幂等，仅管理员可用）")
    @PostMapping("/import")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importDemo() {
        R<DemoImportResultDTO> denied = checkEnabled();
        if (denied != null) return denied;
        return R.ok(demoImportService.importDemoData());
    }

    @Operation(summary = "清除演示数据", description = "清除已导入的演示数据：知识库与回答方案移入回收站（7 天保留），笔记/记忆/应用/公告直接删除（仅管理员可用）")
    @PostMapping("/clear")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> clearDemo() {
        R<DemoImportResultDTO> denied = checkEnabled();
        if (denied != null) return denied;
        return R.ok(demoImportService.clearDemoData());
    }

    @Operation(summary = "导入招投标演示环境", description = "一键导入招投标演示：招标文件知识库（4 篇脱敏招标文件）+ 示例投标项目（可直接触发解读，幂等，仅管理员可用）")
    @PostMapping("/import-bid")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importBidDemo() {
        R<DemoImportResultDTO> denied = checkEnabled();
        if (denied != null) return denied;
        return R.ok(bidDemoImportService.importBidDemoData());
    }

    @Operation(summary = "清除招投标演示环境", description = "清除招投标演示数据：示例投标项目删除、招标文件知识库移入回收站（7 天保留，仅管理员可用）")
    @PostMapping("/clear-bid")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> clearBidDemo() {
        R<DemoImportResultDTO> denied = checkEnabled();
        if (denied != null) return denied;
        return R.ok(bidDemoImportService.clearBidDemoData());
    }

    @Operation(summary = "导入行业免费试用样例", description = "导入指定行业方案包的免费试用样例：行业样例知识库（3 篇脱敏招标文件）+ 示例投标项目，与行业方案包离线评测语料同源（幂等，仅管理员可用）")
    @PostMapping("/import-bid-industry")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importBidIndustrySamples(@RequestParam String industry) {
        R<DemoImportResultDTO> denied = checkEnabled();
        if (denied != null) return denied;
        return R.ok(bidDemoImportService.importBidIndustrySamples(industry));
    }
}
