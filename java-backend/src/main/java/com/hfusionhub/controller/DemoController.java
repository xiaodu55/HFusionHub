package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.service.BidDemoImportService;
import com.hfusionhub.service.DemoImportService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 演示数据控制器 — 一键导入各菜单示例数据，帮助新用户快速上手
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

    @Operation(summary = "导入演示数据", description = "一键导入各菜单示例数据：知识库文档、回答方案、我的笔记、我的记忆、应用发布、公告（幂等，仅管理员可用）")
    @PostMapping("/import")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importDemo() {
        return R.ok(demoImportService.importDemoData());
    }

    @Operation(summary = "清除演示数据", description = "清除已导入的演示数据：知识库与回答方案移入回收站（7 天保留），笔记/记忆/应用/公告直接删除（仅管理员可用）")
    @PostMapping("/clear")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> clearDemo() {
        return R.ok(demoImportService.clearDemoData());
    }

    @Operation(summary = "导入招投标演示环境", description = "一键导入招投标演示：招标文件知识库（4 篇脱敏招标文件）+ 示例投标项目（可直接触发解读，幂等，仅管理员可用）")
    @PostMapping("/import-bid")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importBidDemo() {
        return R.ok(bidDemoImportService.importBidDemoData());
    }

    @Operation(summary = "清除招投标演示环境", description = "清除招投标演示数据：示例投标项目删除、招标文件知识库移入回收站（7 天保留，仅管理员可用）")
    @PostMapping("/clear-bid")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> clearBidDemo() {
        return R.ok(bidDemoImportService.clearBidDemoData());
    }
}
