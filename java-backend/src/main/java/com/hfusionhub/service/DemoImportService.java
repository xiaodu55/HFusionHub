package com.hfusionhub.service;

import com.hfusionhub.dto.DemoImportResultDTO;

/**
 * 演示数据服务 - 一键导入各菜单示例数据，帮助新用户快速体验平台能力
 *
 * @author HFusionHub Team
 */
public interface DemoImportService {

    /**
     * 导入演示数据（幂等）：知识库（文档）、回答方案、我的笔记、我的记忆、应用发布、公告。
     * 每类数据按名称/标题判重，可重复调用。
     *
     * @return 导入结果（含分项计数）
     */
    DemoImportResultDTO importDemoData();
}
