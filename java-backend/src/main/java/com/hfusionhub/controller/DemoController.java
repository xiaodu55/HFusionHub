package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.DemoImportResultDTO;
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

    @Operation(summary = "导入演示数据", description = "一键导入各菜单示例数据：知识库文档、回答方案、我的笔记、我的记忆、应用发布、公告（幂等，仅管理员可用）")
    @PostMapping("/import")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importDemo() {
        return R.ok(demoImportService.importDemoData());
    }
}
