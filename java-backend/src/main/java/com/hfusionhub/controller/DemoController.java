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
 * 演示数据控制器 — 一键导入示例知识库，帮助新用户快速上手
 *
 * @author HFusionHub Team
 */
@Tag(name = "演示数据", description = "演示知识库一键导入")
@RestController
@RequestMapping("/demo")
@RequiredArgsConstructor
public class DemoController {

    private final DemoImportService demoImportService;

    @Operation(summary = "导入演示知识库", description = "创建/复用演示知识库并导入内置示例文档（幂等，仅管理员可用）")
    @PostMapping("/import")
    @SaCheckRole("admin")
    public R<DemoImportResultDTO> importDemo() {
        return R.ok(demoImportService.importDemoKnowledgeBase());
    }
}
